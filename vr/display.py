"""Keeps the panel on the wrist: joins SteamVR when it runs, sends the picture when it changed,
follows the controller, and fades the panel in while its wearer looks at it."""
from __future__ import annotations

import math
import os
import time

import numpy as np
from PySide6.QtCore import QObject, Qt, QTimer, Signal

from . import config, pose
from .config import VrSettings
from .diagnostics import Diagnostics
from .overlay import Lost, WristOverlay
from .panel import SIZE, WristPanel, cursor_image, rgba

CURSOR_TICK_MS = 8     # 120–125 Hz: the aiming cursor follows the other controller every tick
IDLE_TICK_MS = 1000   # no poses or pointer to follow while disabled or SteamVR is absent
RETRY_S = 3.0          # between two tries to join SteamVR
AFTER_QUIT_S = 15.0    # SteamVR takes a while to close; joining it meanwhile would hold it open
SETTLE_S = 0.12        # the picture is sent this long after the last change (a line arrives in pieces)
FADE_PER_S = 5.0
SCROLL_PX_PER_S = 600.0
MAX_ELAPSED_S = 0.1
RENDER_INTERVAL_S = 1 / 30   # cap for the panel's slower work: events, attach and picture
EDGE_GRACE_S = 0.075
EDGE_GRACE_PX = 3
HOLD_GRACE_S = 0.4     # a twitch of the head must not drop a cursor or press that is already placed
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
        self._ticked_at = None
        self._rendered_at = None
        self._panel_at = None            # when SteamVR's messages and the attach were last read
        self._scroll_residual = 0.0
        self._visual_uv = None
        self._last_hit_at = None
        self._engaged_at = None          # when the gaze and the fade last allowed interaction
        self._scrolling = False          # the panel is being scrolled by the thumbstick
        self._scrolled = False           # a scroll wants its frame at the render rate, not at once
        self._diagnostics = Diagnostics() if os.environ.get("VRCT_VR_DIAGNOSTICS") == "1" else None
        panel.changed.connect(self._panel_changed)
        panel.interaction_changed.connect(self._interaction_changed)
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.timeout.connect(self.tick)

    def start(self) -> None:
        self._timer.start(self._tick_interval())

    def _tick_interval(self) -> int:
        return CURSOR_TICK_MS if self.settings.enabled and self.overlay.connected else IDLE_TICK_MS

    def stop(self) -> None:
        self._timer.stop()
        self._reset_runtime("stop")
        self.overlay.close()

    def settings_changed(self) -> None:
        self.settings.clean()
        try:
            self._save(self.settings)
        except OSError:
            pass   # a read-only settings file must not break the display
        self._urgent = True
        self._panel_at = None            # a new place or look reaches SteamVR at once
        self.tick()

    def _panel_changed(self) -> None:
        self._dirty = True
        self._changed_at = self._clock()

    def _panel_due(self, now: float) -> bool:
        """Whether this tick also does the panel's slower work: SteamVR's events, the attach and
        the picture. The cursor path runs on every tick regardless."""
        return (self._panel_at is None or now < self._panel_at
                or now - self._panel_at >= RENDER_INTERVAL_S)

    def _interaction_changed(self) -> None:
        # A press or a switch is drawn at once; thumbstick scrolling only asks for the next
        # frame at the render rate, so a moving stick cannot force back-to-back redraws.
        self._dirty = True
        if not self._scrolling:
            self._urgent = True
            self._panel_at = None

    def _cancel_pointer(self, reason: str = "cancel") -> None:
        if self._diagnostics is not None:
            self._diagnostics.loss(reason)
        self._input_armed = False
        self._pointing_hand = None
        self._scroll_residual = 0.0
        self._visual_uv = self._last_hit_at = self._engaged_at = None
        self.panel.point(None)

    def _reset_runtime(self, reason: str) -> None:
        self._cancel_pointer(reason)
        self._ticked_at = self._rendered_at = self._panel_at = None
        self._scrolled = False
        self._amount = 0.0
        self._looking = False

    def _interact(self, world_panel, now: float, elapsed: float, valid: bool = True) -> None:
        if world_panel is None or not valid:
            self._cancel_pointer("tracking")   # no usable pose: the interaction ends at once
            return
        engaged = self._looking and self._amount >= 0.5
        if engaged:
            self._engaged_at = now
        # A twitch of the head, or a fade that dipped for a moment, must not drop a cursor that
        # is still on the panel: the interaction is kept for HOLD_GRACE_S after the wearer was
        # last looking at it. A longer look-away cancels it, and so does a ray that leaves.
        holding = (not engaged and self._engaged_at is not None
                   and self.panel.pointer[0] is not None
                   and now - self._engaged_at <= HOLD_GRACE_S)
        if not engaged and not holding:
            self._cancel_pointer("gaze_or_fade")
            return
        other = "right" if self.settings.hand == "left" else "left"
        if other != self._pointing_hand:
            self._cancel_pointer("hand_changed")
            self._pointing_hand = other
        state = self.overlay.pointer_state(other)
        if state is None:
            self._cancel_pointer("tracking_or_input")
            return
        aim, held, scroll = state
        if not math.isfinite(scroll):
            self._cancel_pointer("invalid_input")
            return
        uv = pose.pointer_coordinates(aim, world_panel, self.settings.width_cm / 100, SIZE[1] / SIZE[0])
        if uv is None or not (0 <= uv[0] < 1 and 0 <= uv[1] < 1):
            if not engaged:
                self._cancel_pointer("gaze_or_fade")   # the ray left while the wearer looked away
                return
            self.panel.point(None)
            self._input_armed = not held
            self._scroll_residual = 0.0
            # Distance to the rectangle also bounds diagonal misses at its corners.
            # SteamVR poses are float32; allow a thousandth of a pixel of roundoff.
            near_edge = (uv is not None and math.hypot(
                max(0.0, -uv[0], uv[0] - 1) * SIZE[0],
                max(0.0, -uv[1], uv[1] - 1) * SIZE[1]) <= EDGE_GRACE_PX + 0.001)
            if not (near_edge and self._last_hit_at is not None
                    and 0 <= now - self._last_hit_at <= EDGE_GRACE_S):
                self._visual_uv = self._last_hit_at = None
            if self._diagnostics is not None:
                self._diagnostics.loss("edge_miss" if near_edge else "invalid_ray_or_miss")
            return
        # A trigger held before looking/pointing/reconnecting must be released before it can click.
        if not held:
            self._input_armed = True
        elif holding and not self.panel.pointer[1]:
            self._input_armed = False      # a look-away keeps a press going but never starts one
        self.panel.point(uv, held and self._input_armed)
        self._visual_uv = self.panel.pointer[0]
        self._last_hit_at = now
        if abs(scroll) > 0.2:
            self._scroll_residual -= max(-1, min(1, scroll)) * SCROLL_PX_PER_S * elapsed
            # Avoid losing an integral pixel to floating point clock subtraction.
            pixels = math.trunc(self._scroll_residual + math.copysign(1e-9, self._scroll_residual))
            self._scroll_residual -= pixels
            if pixels:
                self._scrolling = True
                try:
                    self.panel.scroll(pixels)
                finally:
                    self._scrolling = False
                # One redraw per RENDER_INTERVAL_S however fast the thumbstick is read.
                self._dirty = self._scrolled = True
        else:
            self._scroll_residual = 0.0

    def _send_pointer(self) -> None:
        _, held = self.panel.pointer
        cursor = cursor_image(held)
        self.overlay.set_pointer(self._visual_uv, rgba(cursor), cursor.width(),
                                 self.settings.opacity / 100 * self._amount)

    def _render(self) -> None:
        started = time.perf_counter() if self._diagnostics is not None else None
        picture = self.panel.image(include_pointer=False)
        data = rgba(picture)
        if self._diagnostics is not None:
            self._diagnostics.sample("render", time.perf_counter() - started)
        if data != self._sent:
            started = time.perf_counter() if self._diagnostics is not None else None
            self.overlay.set_image(data, picture.width(), picture.height())
            if self._diagnostics is not None:
                self._diagnostics.sample("upload", time.perf_counter() - started)
            self._sent = data
        self._dirty = self._urgent = self._scrolled = False

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
        # Languages, switches and text size are discrete settings: draw them now rather
        # than waiting for the settle delay that batches arriving subtitle text.
        self._urgent = True
        self.panel.set_look(look[0], look[2], look[1])
        self.panel.set_switches(look[3], look[4])
        self.panel.set_languages(list(look[6]), list(look[7]))
        if language_changed:
            self.panel.retranslate()
            self.language_changed.emit(look[5])

    def tick(self) -> None:
        now = self._clock()
        if self._diagnostics is not None:
            self._diagnostics.callback(now)
        try:
            self._tick(now)
        finally:
            if self._diagnostics is not None:
                self._diagnostics.flush(now)
            interval = self._tick_interval()
            if self._timer.interval() != interval:
                self._timer.setInterval(interval)

    def _tick(self, now: float) -> None:
        self._follow_settings()
        s = self.settings
        if not s.enabled:
            self._reset_runtime("disabled")
            self.overlay.close()
            self.problem = ""
            self._set_state(OFF)
            return
        try:
            if not self.overlay.connected:
                self._reset_runtime("disconnected")
                if now < self._retry_at:
                    return
                self._retry_at = now + RETRY_S
                if not self._running():
                    self.problem = ""
                    self._set_state(WAITING)
                    return
                self.overlay.connect()
                self._attached = self._sent = None
                self._dirty, self._amount = True, 0.0
                self._looking = False
            # The panel's own work (SteamVR's messages and its place) is capped at the render
            # rate; the aiming ray, the fade and the cursor are cheap and follow every tick.
            panel = self._panel_due(now)
            if panel:
                self._panel_at = now
                if not self.overlay.poll():
                    self._reset_runtime("disconnected")
                    self._retry_at = now + AFTER_QUIT_S
                    self._set_state(WAITING)
                    return
            device = self.overlay.controller(s.hand)
            if device is None:
                self._reset_runtime("controller_off")
                self.overlay.show(0.0)
                self._amount = 0.0
                self._looking = False
                self._set_state(NO_CONTROLLER)
                return
            elapsed = (min(MAX_ELAPSED_S, max(0.0, now - self._ticked_at))
                       if self._ticked_at is not None else 0.0)
            if self._ticked_at is None or now > self._ticked_at:
                self._ticked_at = now
            if panel:
                placement = (device, s.hand, s.width_cm, s.along_cm, s.out_cm, s.up_cm,
                             s.tilt_deg, s.yaw_deg, s.roll_deg)
                if placement != self._attached:
                    self._cancel_pointer("placement_changed")
                    self._transform = pose.wrist_transform(s.hand, s.along_cm, s.out_cm, s.up_cm,
                                                          s.tilt_deg, s.yaw_deg, s.roll_deg)
                    self.overlay.attach(device, self._transform, s.width_cm / 100)
                    self._attached = placement
            head, hand = self.overlay.poses(HEADSET, device)
            world_panel = pose.compose(hand, self._transform) if hand is not None else None
            # A pose SteamVR cannot make sense of fails closed; a headset that is briefly
            # untracked is a look-away like any other, so its cursor may stay for a moment.
            valid = head is None or bool(np.isfinite(head).all())
            gaze = (pose.looked_at(head, world_panel)
                    if valid and head is not None and world_panel is not None else 0.0)
            self._looking = gaze >= (LOOK_LEAVE if self._looking else LOOK_ENTER)
            wanted = float(self._looking) if s.look_only else 1.0
            was_hidden = self._amount <= 0.01
            fade = FADE_PER_S * elapsed
            self._amount += min(max(wanted - self._amount, -fade), fade)
            self._interact(world_panel, now, elapsed, valid)
            self._follow_settings()
            # The first cursor needs the panel image dimensions. Initialize that texture
            # before sending a cursor; all subsequent feedback precedes panel drawing.
            first_picture = self._amount > 0.01 and self._sent is None
            if first_picture:
                self._render()
                self._rendered_at = now
            self.overlay.show(s.opacity / 100 * self._amount)
            self._send_pointer()
            # Keep changes pending while the wrist is out of view. Render the latest text
            # immediately on reveal, avoiding CPU drawing and GPU uploads the wearer cannot see.
            if (self._amount > 0.01 and self._dirty
                    and (was_hidden or self._rendered_at is None
                         or now - self._rendered_at >= RENDER_INTERVAL_S) and (
                    was_hidden or self._urgent or self._scrolled or self._sent is None
                    or now - self._changed_at >= SETTLE_S)):
                self._render()
                self._rendered_at = now
            self.problem = self.overlay.input_problem
            self._set_state(ON)
        except Lost as error:
            self._reset_runtime("disconnected")
            self.problem = str(error)
            self._retry_at = now + RETRY_S
            self._set_state(WAITING)
