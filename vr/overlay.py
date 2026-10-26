"""The link to SteamVR: a subtitle overlay and a separate cursor following a controller.

The program joins SteamVR as an overlay app: it never starts SteamVR, it only joins when
SteamVR is already running, and it lets go when SteamVR closes. Display calls raise Lost
when the link breaks; input errors are reported without interrupting the subtitles.
"""
from __future__ import annotations

import functools
import time
from pathlib import Path

import numpy as np

from .texture import OverlayTextures, TextureError

KEY = "sentominh.vr-translator.wrist"    # SteamVR knows the overlay by this
NAME = "VR Translator"
INPUT_RETRY_S = 3.0


class Lost(Exception):
    """SteamVR is not there (any more)."""


def _steamvr_call(method):
    @functools.wraps(method)
    def call(self, *args, **kwargs):
        if not self.connected:
            raise Lost("SteamVR is not connected")
        try:
            return method(self, *args, **kwargs)
        except (self._vr.OpenVRError, TextureError) as error:
            self.close()
            raise Lost(_reason(error)) from error
    return call


def _reason(error: Exception) -> str:
    return str(error) or type(error).__name__


class WristOverlay:
    def __init__(self, vr=None):
        self._vr = vr              # the openvr module; loaded when first needed
        self._system = None
        self._overlay = None
        self._handle = None
        self._poses = None
        self._shown = False
        self._cursor = None
        self._cursor_shown = False
        self._cursor_image = None
        self._input = None
        self._textures = None
        self._input_retry_at = 0.0
        self.input_problem = ""

    @property
    def connected(self) -> bool:
        return self._handle is not None

    def connect(self) -> None:
        """Joins SteamVR and makes the (still hidden) overlay. Raises Lost when SteamVR is not
        running or the SteamVR library is missing."""
        if self.connected:
            return
        if self._vr is None:
            try:
                import openvr
            except Exception as error:       # the library or its DLL is missing
                raise Lost(f"the SteamVR library did not load ({_reason(error)})") from error
            self._vr = openvr
        vr = self._vr
        try:
            self._system = vr.init(vr.VRApplication_Overlay)
        except vr.OpenVRError as error:
            self._system = None
            raise Lost(_reason(error)) from error
        try:
            self._overlay = vr.VROverlay()
            try:
                self._handle = self._overlay.createOverlay(KEY, NAME)
            except vr.OpenVRError:
                # left behind by a copy of the program that did not close cleanly
                self._handle = self._overlay.findOverlay(KEY)
            self._poses = (vr.TrackedDevicePose_t * vr.k_unMaxTrackedDeviceCount)()
        except vr.OpenVRError as error:
            self.close()
            raise Lost(_reason(error)) from error
        self._shown = False
        self.input_problem = ""
        self._prepare_input()

    def _prepare_input(self) -> None:
        vr = self._vr
        self._input_retry_at = time.monotonic() + INPUT_RETRY_S
        try:
            inputs = vr.VRInput()
            inputs.setActionManifestPath(str(Path(__file__).resolve().parent.parent / "assets/vr/actions.json"))
            self._actions = {name: inputs.getActionHandle(f"/actions/wrist/in/{name}")
                             for name in ("point", "click", "scroll")}
            self._sources = {hand: inputs.getInputSourceHandle(f"/user/hand/{hand}") for hand in ("left", "right")}
            self._action_sets = (vr.VRActiveActionSet_t * 1)()
            self._action_sets[0].ulActionSet = inputs.getActionSetHandle("/actions/wrist")
            self._input = inputs
            self.input_problem = ""
        except vr.OpenVRError as error:
            self.input_problem = _reason(error)
            self._input = None

    def close(self) -> None:
        if self._vr is None or self._system is None:
            return
        try:
            if self._cursor is not None:
                self._overlay.destroyOverlay(self._cursor)
        except self._vr.OpenVRError:
            pass
        try:
            if self._handle is not None:
                self._overlay.destroyOverlay(self._handle)
        except self._vr.OpenVRError:
            pass
        try:
            self._vr.shutdown()
        except self._vr.OpenVRError:
            pass
        self._system = self._overlay = self._handle = self._poses = None
        self._input = None
        self._shown = False
        self._cursor = self._cursor_image = None
        self._cursor_shown = False

        if self._textures is not None:
            self._textures.close()
            self._textures = None

    def pointer_state(self, hand: str):
        """Aim pose, trigger and scroll from the opposite controller's SteamVR bindings.

        An input failure must not take down translated subtitles.
        """
        if not self.connected or self._input is None:
            return None
        vr, inputs = self._vr, self._input
        source = self._sources[hand]
        try:
            self._action_sets[0].ulRestrictedToDevice = source
            inputs.updateActionState(self._action_sets)
            point = inputs.getPoseActionDataRelativeToNow(
                self._actions["point"], vr.TrackingUniverseStanding, 0, source)
            click = inputs.getDigitalActionData(self._actions["click"], source)
            scroll = inputs.getAnalogActionData(self._actions["scroll"], source)
            self.input_problem = ""
            if not point.bActive or not point.pose.bPoseIsValid or not click.bActive:
                return None
            matrix = point.pose.mDeviceToAbsoluteTracking.m
            aim = np.array([[matrix[r][c] for c in range(4)] for r in range(3)], dtype=float)
            return aim, bool(click.bState), float(scroll.y) if scroll.bActive else 0.0
        except vr.OpenVRError as error:
            self.input_problem = _reason(error)
            return None

    @_steamvr_call
    def poll(self) -> bool:
        """Reads SteamVR's messages. False = SteamVR is closing; the link is let go at once
        (SteamVR ends programs that hold on while it closes)."""
        vr = self._vr
        if self._input is None and time.monotonic() >= self._input_retry_at:
            self._prepare_input()
        event = vr.VREvent_t()
        while self._system.pollNextEvent(event):
            if event.eventType == vr.VREvent_Quit:
                self._system.acknowledgeQuit_Exiting()
                self.close()
                return False
        return True

    @_steamvr_call
    def controller(self, hand: str) -> int | None:
        """SteamVR's number for the left or right controller; None while it is switched off."""
        vr = self._vr
        role = vr.TrackedControllerRole_LeftHand if hand == "left" else vr.TrackedControllerRole_RightHand
        index = self._system.getTrackedDeviceIndexForControllerRole(role)
        return None if index == vr.k_unTrackedDeviceIndexInvalid else int(index)

    @_steamvr_call
    def attach(self, device: int, transform: np.ndarray, width_m: float) -> None:
        """Fixes the overlay to a tracked device; `transform` (3 × 4) is its pose relative to
        the device (vr/pose.py)."""
        matrix = self._vr.HmdMatrix34_t()
        for row in range(3):
            for column in range(4):
                matrix.m[row][column] = float(transform[row][column])
        self._overlay.setOverlayTransformTrackedDeviceRelative(self._handle, device, matrix)
        self._overlay.setOverlayWidthInMeters(self._handle, width_m)
        self._placement = (device, transform.copy(), width_m)

    @_steamvr_call
    def set_image(self, rgba: bytes, width: int, height: int) -> None:
        """The picture: 4 bytes a pixel (red, green, blue, opacity), top row first."""
        self._upload(self._handle, rgba, width, height)
        self._image_size = (width, height)

    def _upload(self, handle, rgba, width, height) -> None:
        if self._textures is None:
            self._textures = OverlayTextures()
        self._textures.submit(self._vr, self._overlay, handle, rgba, width, height)

    @_steamvr_call
    def set_pointer(self, uv, rgba: bytes, size: int, opacity: float) -> None:
        """Move a small separate cursor; aiming must not replace the subtitle texture."""
        if uv is None or opacity <= 0.01:
            self._hide_pointer()
            return
        if self._cursor is None:
            self._cursor = self._overlay.createOverlay(KEY + ".cursor", NAME + " cursor")
            self._overlay.setOverlaySortOrder(self._cursor, 1)
        if rgba != self._cursor_image:
            self._upload(self._cursor, rgba, size, size)
            self._cursor_image = rgba
        device, transform, width_m = self._placement
        pixels_w, pixels_h = self._image_size
        # Offset toward the viewer to keep the two surfaces from fighting for depth.
        offset = np.array([(uv[0] - 0.5) * width_m,
                           (0.5 - uv[1]) * width_m * pixels_h / pixels_w, 0.001])
        cursor = transform.copy()
        cursor[:, 3] += transform[:, :3] @ offset
        matrix = self._vr.HmdMatrix34_t()
        for row in range(3):
            for column in range(4):
                matrix.m[row][column] = float(cursor[row][column])
        self._overlay.setOverlayTransformTrackedDeviceRelative(self._cursor, device, matrix)
        self._overlay.setOverlayWidthInMeters(self._cursor, width_m * size / pixels_w)
        self._overlay.setOverlayAlpha(self._cursor, min(float(opacity), 1.0))
        if not self._cursor_shown:
            self._overlay.showOverlay(self._cursor)
            self._cursor_shown = True

    def _hide_pointer(self) -> None:
        if self._cursor_shown:
            self._overlay.hideOverlay(self._cursor)
            self._cursor_shown = False

    @_steamvr_call
    def show(self, opacity: float) -> None:
        """0.0 hides the overlay; above that it is shown that see-through."""
        if opacity <= 0.01:
            self._hide_pointer()
            if self._shown:
                self._overlay.hideOverlay(self._handle)
                self._shown = False
            return
        self._overlay.setOverlayAlpha(self._handle, min(float(opacity), 1.0))
        if not self._shown:
            self._overlay.showOverlay(self._handle)
            self._shown = True

    @_steamvr_call
    def poses(self, *devices: int) -> list[np.ndarray | None]:
        """Where the headset (device 0) and other devices are in the room right now; None for
        one that is not tracked at the moment."""
        vr = self._vr
        self._system.getDeviceToAbsoluteTrackingPose(vr.TrackingUniverseStanding, 0, self._poses)
        answer = []
        for device in devices:
            pose = self._poses[device]
            if not pose.bPoseIsValid:
                answer.append(None)
                continue
            answer.append(np.array([[pose.mDeviceToAbsoluteTracking.m[row][column]
                                     for column in range(4)] for row in range(3)], dtype=float))
        return answer
