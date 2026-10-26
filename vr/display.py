"""Keeps the panel on the wrist: joins SteamVR when it runs, sends the picture when it changed,
follows the controller, and fades the panel in while its wearer looks at it."""
from __future__ import annotations

import time

from PySide6.QtCore import QObject, QTimer, Signal

from . import config, pose
from .config import VrSettings
from .overlay import Lost, WristOverlay
from .panel import SIZE, WristPanel, cursor_image, rgba

TICK_MS = 50
RETRY_S = 3.0          # between two tries to join SteamVR
AFTER_QUIT_S = 15.0    # SteamVR takes a while to close; joining it meanwhile would hold it open
SETTLE_S = 0.12        # the picture is sent this long after the last change (a line arrives in pieces)
FADE = 0.25            # of full opacity per tick
LOOK_ENTER = 0.5
LOOK_LEAVE = 0.3       # separate thresholds prevent wrist jitter from toggling input/visibility
HEADSET = 0            # SteamVR's device number of the headset

OFF = "Off"
WAITING = "Waiting for SteamVR"
NO_CONTROLLER = "SteamVR is running; that controller is off"
ON = "On your wrist"


def steamvr_running() -> bool:
    from vrc.chatbox import process_ids
    return bool(process_ids("vrserver.exe"))


class WristDisplay(QObject):
    state_changed = Signal(str)      # OFF, WAITING, NO_CONTROLLER or ON
    language_changed = Signal(str)

    def __init__(self, panel: WristPanel, settings: VrSettings, window_settings=lambda: None,
                 overlay: WristOverlay | None = None, save=config.save, clock=time.monotonic,
                 running=steamvr_running):
        super().__init__()
        self.panel = panel
        self.settings = settings
        self.overlay = overlay or WristOverlay()
        self.state = OFF
        self.problem = ""                # why SteamVR could not be joined, for the settings
        self._window_settings = window_settings   # the window's Settings (ui/config.py), or None
        self._save = save
        self._clock = clock
        self._running = running
        self._retry_at = 0.0
        self._attached = None            # (device, hand, size and place) SteamVR was last told
        self._transform = None
        self._look = None
        self._dirty = True
        self._changed_at = 0.0
        self._sent = None
        self._amount = 0.0               # 0.0 – 1.0: how far the panel has faded in
        self._looking = False
        self._urgent = False
        self._input_armed = False
        self._pointing_hand = None
        self._reported = None
        panel.changed.connect(self._panel_changed)
        panel.interaction_changed.connect(self._interaction_changed)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.tick)

    def start(self) -> None:
        self._timer.start(TICK_MS)

    def stop(self) -> None:
        self._timer.stop()
        self._cancel_pointer()
        self.overlay.close()

    def settings_changed(self) -> None:
        self.settings.clean()
        try:
            self._save(self.settings)
        except OSError:
            pass   # a read-only settings file must not break the display
        self._urgent = True
        self.tick()

    def _panel_changed(self) -> None:
        self._dirty = True
        self._changed_at = self._clock()

    def _interaction_changed(self) -> None:
        self._dirty = self._urgent = True

    def _cancel_pointer(self) -> None:
        self._input_armed = False
        self._pointing_hand = None
        self.panel.point(None)

    def _interact(self, world_panel) -> None:
        if world_panel is None or not self._looking or self._amount < 0.5:
            self._cancel_pointer()
            return
        other = "right" if self.settings.hand == "left" else "left"
        if other != self._pointing_hand:
            self._cancel_pointer()
            self._pointing_hand = other
        state = self.overlay.pointer_state(other)
        if state is None:
            self._cancel_pointer()
            return
        aim, held, scroll = state
        uv = pose.pointer_hit(aim, world_panel, self.settings.width_cm / 100, SIZE[1] / SIZE[0])
        if uv is None:
            self.panel.point(None)
            self._input_armed = not held
            return
        # A trigger held before looking/pointing/reconnecting must be released before it can click.
        if not held:
            self._input_armed = True
        self.panel.point(uv, held and self._input_armed)
        if abs(scroll) > 0.2:
            self.panel.scroll(-round(max(-1, min(1, scroll)) * 30))

    def _set_state(self, state: str) -> None:
        self.state = state
        report = (state, self.problem)
        if report != self._reported:
            self._reported = report
            self.state_changed.emit(state)

    def _follow_settings(self) -> None:
        """The panel takes its text size and darkness from the wrist settings and the rest
        (heard text shown or not, language, the two switches) from the window's."""
        s, window = self.settings, self._window_settings()
        look = (s.font_px, s.backdrop, getattr(window, "show_original", True),
                getattr(window, "mic_on", True), getattr(window, "subtitles_on", True),
                getattr(window, "ui_lang", "en"),
                tuple(window.spoken_languages(True)) if window else ("vi",),
                tuple(window.spoken_languages(False)) if window else ("auto",))
        if look == self._look:
            return
        language_changed = self._look is not None and look[5] != self._look[5]
        self._look = look
        self.panel.set_look(look[0], look[2], look[1])
        self.panel.set_switches(look[3], look[4])
        self.panel.set_languages(list(look[6]), list(look[7]))
        if language_changed:
            self.panel.retranslate()
            self.language_changed.emit(look[5])

    def tick(self) -> None:
        self._follow_settings()
        s, now = self.settings, self._clock()
        if not s.enabled:
            self._cancel_pointer()
            self.overlay.close()
            self.problem = ""
            self._set_state(OFF)
            return
        try:
            if not self.overlay.connected:
                if now < self._retry_at:
                    return
                self._retry_at = now + RETRY_S
                if not self._running():
                    self.problem = ""
                    self._set_state(WAITING)
                    return
                self.overlay.connect()
                self._cancel_pointer()
                self._attached = self._sent = None
                self._dirty, self._amount = True, 0.0
                self._looking = False
            if not self.overlay.poll():
                self._cancel_pointer()
                self._retry_at = now + AFTER_QUIT_S
                self._set_state(WAITING)
                return
            device = self.overlay.controller(s.hand)
            if device is None:
                self._cancel_pointer()
                self.overlay.show(0.0)
                self._amount = 0.0
                self._looking = False
                self._set_state(NO_CONTROLLER)
                return
            placement = (device, s.hand, s.width_cm, s.along_cm, s.out_cm, s.up_cm,
                         s.tilt_deg, s.yaw_deg, s.roll_deg)
            if placement != self._attached:
                self._transform = pose.wrist_transform(s.hand, s.along_cm, s.out_cm, s.up_cm,
                                                      s.tilt_deg, s.yaw_deg, s.roll_deg)
                self.overlay.attach(device, self._transform, s.width_cm / 100)
                self._attached = placement
            head, hand = self.overlay.poses(HEADSET, device)
            world_panel = pose.compose(hand, self._transform) if hand is not None else None
            gaze = pose.looked_at(head, world_panel) if head is not None and world_panel is not None else 0.0
            self._looking = gaze >= (LOOK_LEAVE if self._looking else LOOK_ENTER)
            wanted = float(self._looking) if s.look_only else 1.0
            self._amount += min(max(wanted - self._amount, -FADE), FADE)
            self._interact(world_panel)
            self._follow_settings()
            if self._dirty and (self._urgent or self._sent is None or now - self._changed_at >= SETTLE_S):
                picture = self.panel.image(include_pointer=False)
                data = rgba(picture)
                if data != self._sent:
                    self.overlay.set_image(data, picture.width(), picture.height())
                    self._sent = data
                self._dirty = False
                self._urgent = False
            self.overlay.show(s.opacity / 100 * self._amount)
            uv, held = self.panel.pointer
            cursor = cursor_image(held)
            self.overlay.set_pointer(uv, rgba(cursor), cursor.width(), s.opacity / 100 * self._amount)
            self.problem = self.overlay.input_problem
            self._set_state(ON)
        except Lost as error:
            self._cancel_pointer()
            self.problem = str(error)
            self._retry_at = now + RETRY_S
            self._set_state(WAITING)
