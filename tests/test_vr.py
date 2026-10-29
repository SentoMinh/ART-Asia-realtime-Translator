"""The wrist display (vr/): placement maths, the link to SteamVR against a pretend SteamVR,
the panel's picture, its settings and its button in the window."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import openvr          # only its plain data types; SteamVR itself is never touched
import pytest
from PySide6.QtWidgets import QApplication

from ui.backend import Backend, Status, Utterance
from ui.config import Settings
from ui.main_window import MainWindow, TitleBar
from vr import config, display, pose
from vr.config import VrSettings
from vr.display import WristDisplay
from vr.main import add_vr_button
from vr.main import bind_wrist_controls
from vr.overlay import Lost, WristOverlay
from vr.panel import SIZE, WristPanel, rgba
from vr.settings_dialog import VrDialog

LEFT, RIGHT = 3, 4     # the pretend SteamVR's device numbers of the two controllers


class FakeTextures:
    def __init__(self):
        self.ids = {}
        self.closed = False

    def submit(self, vr, overlay, handle, data, width, height):
        assert not self.closed
        texture_id = self.ids.setdefault(handle, len(self.ids) + 1)
        vr.texture_data[texture_id] = (data, width, height, 4)
        overlay.setOverlayTexture(handle, openvr.Texture_t(texture_id, openvr.TextureType_OpenGL,
                                                         openvr.ColorSpace_Gamma))

    def close(self):
        self.closed = True


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


def room_pose(position, right=(1, 0, 0), up=(0, 1, 0), back=(0, 0, 1)) -> np.ndarray:
    return np.column_stack([right, up, back, position]).astype(float)


class FakeVR:
    """Stands in for the openvr module: SteamVR that can be started, closed and made to fail."""
    VRApplication_Background = openvr.VRApplication_Background
    VRApplication_Overlay = openvr.VRApplication_Overlay
    VRActiveActionSet_t = openvr.VRActiveActionSet_t
    VREvent_Quit = openvr.VREvent_Quit
    TrackedControllerRole_LeftHand = openvr.TrackedControllerRole_LeftHand
    TrackedControllerRole_RightHand = openvr.TrackedControllerRole_RightHand
    k_unTrackedDeviceIndexInvalid = openvr.k_unTrackedDeviceIndexInvalid
    k_unMaxTrackedDeviceCount = openvr.k_unMaxTrackedDeviceCount
    TrackingUniverseStanding = openvr.TrackingUniverseStanding
    HmdMatrix34_t = openvr.HmdMatrix34_t
    TrackedDevicePose_t = openvr.TrackedDevicePose_t
    VREvent_t = openvr.VREvent_t

    class OpenVRError(Exception):
        pass

    def __init__(self):
        self.running = True
        self.inits = self.shutdowns = 0
        self.events: list[int] = []
        self.controllers = {self.TrackedControllerRole_LeftHand: LEFT,
                            self.TrackedControllerRole_RightHand: RIGHT}
        # the headset at eye height looking straight ahead; the controllers not tracked yet
        self.room = {0: room_pose((0, 1.6, 0))}
        self.key_in_use = False
        self.fail = ""                 # name of a call that raises
        self.created, self.destroyed, self.images, self.attached = [], [], [], []
        self.alpha, self.width, self.shown = None, None, False
        self.aims, self.triggers, self.scrolls = {}, {}, {}
        self.input_active = True
        self.input_sources = []
        self.cursor_images, self.cursor_attached = [], []
        self.cursor_shown = False
        self.texture_data, self.texture_ids = {}, {}
        self.hidden = []

    def _maybe_fail(self, name):
        if self.fail == name:
            raise self.OpenVRError(f"{name} failed")

    # the module
    def init(self, kind):
        self.app_kind = kind
        self.inits += 1
        if not self.running:
            raise self.OpenVRError("no SteamVR")
        return self

    def VROverlay(self):
        return self

    def VRInput(self):
        return self

    def setActionManifestPath(self, path):
        self.manifest = path

    def getActionHandle(self, name):
        self._maybe_fail("getActionHandle")
        return name

    def getInputSourceHandle(self, name):
        return LEFT if name.endswith("left") else RIGHT

    def getActionSetHandle(self, name):
        return 1

    def updateActionState(self, sets):
        self.input_sources.append(sets[0].ulRestrictedToDevice)

    def getPoseActionDataRelativeToNow(self, action, origin, seconds, source):
        result = openvr.InputPoseActionData_t()
        result.bActive = self.input_active
        where = self.aims.get(source)
        result.pose.bPoseIsValid = where is not None
        if where is not None:
            for row in range(3):
                for column in range(4):
                    result.pose.mDeviceToAbsoluteTracking.m[row][column] = where[row][column]
        return result

    def getDigitalActionData(self, action, source):
        self._maybe_fail("getDigitalActionData")
        result = openvr.InputDigitalActionData_t()
        result.bActive = self.input_active
        result.bState = self.triggers.get(source, False)
        return result

    def getAnalogActionData(self, action, source):
        result = openvr.InputAnalogActionData_t()
        result.bActive = self.input_active
        result.y = self.scrolls.get(source, 0)
        return result

    def shutdown(self):
        self.shutdowns += 1

    # IVRSystem
    def pollNextEvent(self, event):
        self._maybe_fail("pollNextEvent")
        if not self.events:
            return False
        event.eventType = self.events.pop(0)
        return True

    def acknowledgeQuit_Exiting(self):
        self.running = False

    def getTrackedDeviceIndexForControllerRole(self, role):
        return self.controllers.get(role, self.k_unTrackedDeviceIndexInvalid)

    def getDeviceToAbsoluteTrackingPose(self, origin, seconds, poses):
        for device in range(len(poses)):
            where = self.room.get(device)
            poses[device].bPoseIsValid = where is not None
            if where is not None:
                for row in range(3):
                    for column in range(4):
                        poses[device].mDeviceToAbsoluteTracking.m[row][column] = where[row][column]
        return poses

    # IVROverlay
    def createOverlay(self, key, name):
        if key.endswith(".cursor"):
            self.created.append(key)
            return 79
        if self.key_in_use:
            raise self.OpenVRError("key in use")
        self.created.append(key)
        return 77

    def findOverlay(self, key):
        return 78

    def destroyOverlay(self, handle):
        self.destroyed.append(handle)

    def setOverlayRaw(self, handle, buffer, width, height, depth):
        raise AssertionError("Raw uploads blank the overlay during interaction")

    def setOverlayTexture(self, handle, texture):
        self._maybe_fail("setOverlayTexture")
        assert texture.eType == openvr.TextureType_OpenGL
        self.texture_ids.setdefault(handle, []).append(texture.handle)
        images = self.cursor_images if handle == 79 else self.images
        images.append(self.texture_data[texture.handle])

    def setOverlayTransformTrackedDeviceRelative(self, handle, device, matrix):
        attached = self.cursor_attached if handle == 79 else self.attached
        attached.append((device, np.array([[matrix.m[r][c] for c in range(4)] for r in range(3)])))

    def setOverlayWidthInMeters(self, handle, width):
        if handle == 79:
            self.cursor_width = width
        else:
            self.width = width

    def setOverlaySortOrder(self, handle, order):
        assert handle == 79 and order == 1

    def setOverlayAlpha(self, handle, alpha):
        if handle != 79:
            self.alpha = alpha

    def showOverlay(self, handle):
        if handle == 79:
            self.cursor_shown = True
        else:
            self.shown = True

    def hideOverlay(self, handle):
        self.hidden.append(handle)
        if handle == 79:
            self.cursor_shown = False
        else:
            self.shown = False


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


@pytest.fixture
def steamvr(monkeypatch):
    monkeypatch.setattr("vr.overlay.OverlayTextures", FakeTextures)
    return FakeVR()


@pytest.fixture
def backend(app):
    return Backend()


@pytest.fixture
def wrist(backend, steamvr):
    """A wrist display joined to the pretend SteamVR; `saved` collects what it saves."""
    clock = Clock()
    wrist = WristDisplay(WristPanel(backend), VrSettings(look_only=False), overlay=WristOverlay(steamvr),
                         save=lambda s: wrist.saved.append(VrSettings(**vars(s))), clock=clock,
                         running=lambda: steamvr.running)
    wrist.saved, wrist.clock = [], clock
    return wrist


# ---- placement ----------------------------------------------------------

def test_left_wrist_text_runs_towards_the_fingers_and_faces_out_of_the_back_of_the_hand():
    place = pose.wrist_transform("left", along_cm=12, out_cm=6, up_cm=0, tilt_deg=0)
    assert place[:, 0].tolist() == [0, 0, -1]          # reading direction = where the controller points
    assert place[:, 2].tolist() == [-1, 0, 0]          # faces left, out of the back of the left hand
    assert place[:, 3] == pytest.approx([-0.06, 0, 0.12])


def test_right_wrist_is_the_mirror_image():
    place = pose.wrist_transform("right", along_cm=12, out_cm=6, up_cm=0, tilt_deg=0)
    assert place[:, 0].tolist() == [0, 0, 1]
    assert place[:, 2].tolist() == [1, 0, 0]
    assert place[:, 3] == pytest.approx([0.06, 0, 0.12])


@pytest.mark.parametrize("hand", ["left", "right"])
@pytest.mark.parametrize("tilt", [-90, -30, 0, 45, 90])
def test_the_panel_is_never_mirrored_or_skewed(hand, tilt):
    turn = pose.wrist_transform(hand, 12, 6, 3, tilt)[:, :3]
    assert turn @ turn.T == pytest.approx(np.eye(3), abs=1e-9)
    assert np.linalg.det(turn) == pytest.approx(1.0)       # -1 would show the text mirrored


def test_turning_around_the_wrist_keeps_the_panel_the_same_distance_from_the_arm():
    for tilt in (-90, 0, 60):
        place = pose.wrist_transform("left", along_cm=10, out_cm=8, up_cm=0, tilt_deg=tilt)
        assert np.linalg.norm(place[:2, 3]) == pytest.approx(0.08)   # off the arm's axis
        assert place[2, 3] == pytest.approx(0.10)                    # along it


@pytest.mark.parametrize("hand", ["left", "right"])
def test_extra_rotation_keeps_center_and_unmirrored_text(hand):
    base = pose.wrist_transform(hand, 12, 6, 3, 25)
    sideways = pose.wrist_transform(hand, 12, 6, 3, 25, roll_deg=90)
    assert sideways[:, 0] == pytest.approx(base[:, 1])
    assert sideways[:, 2] == pytest.approx(base[:, 2])
    flipped = pose.wrist_transform(hand, 12, 6, 3, 25, roll_deg=180)
    assert flipped[:, :2] == pytest.approx(-base[:, :2], abs=1e-9)
    tilted = pose.wrist_transform(hand, 12, 6, 3, 25, yaw_deg=90)
    assert tilted[:, 2] == pytest.approx(base[:, 0], abs=1e-9)
    for yaw, roll in ((0, 90), (90, 0), (-180, 180), (35, -70)):
        rotated = pose.wrist_transform(hand, 12, 6, 3, 25, yaw, roll)
        assert rotated[:, 3] == pytest.approx(base[:, 3])
        assert rotated[:, :3].T @ rotated[:, :3] == pytest.approx(np.eye(3), abs=1e-9)
        assert np.linalg.det(rotated[:, :3]) == pytest.approx(1)
        aim = pose.compose(rotated, room_pose((0.03, 0.02, 0.3)))
        assert pose.pointer_hit(aim, rotated, 0.24, 2 / 3) == pytest.approx((0.625, 0.375))


def test_compose_puts_a_relative_pose_into_the_room():
    hand = room_pose((1, 1, 1), right=(0, 0, -1), up=(0, 1, 0), back=(1, 0, 0))   # turned a quarter
    panel = pose.compose(hand, room_pose((0, 0, 0.5)))
    assert panel[:, 3] == pytest.approx([1.5, 1, 1])
    assert panel[:, 2] == pytest.approx([1, 0, 0])


def test_looked_at_needs_the_panel_towards_the_face_and_the_face_towards_the_panel():
    head = room_pose((0, 1.6, 0))                              # looks along -z
    in_front = room_pose((0, 1.6, -0.4))                       # 40 cm ahead, facing the head
    assert pose.looked_at(head, in_front) == 1.0
    turned_away = room_pose((0, 1.6, -0.4), right=(-1, 0, 0), back=(0, 0, -1))
    assert pose.looked_at(head, turned_away) == 0.0
    at_the_hip = room_pose((0.3, 0.9, 0), up=(0, 0, -1), back=(0, 1, 0))   # faces up, head looks ahead
    assert pose.looked_at(head, at_the_hip) == 0.0
    edge_on = room_pose((0, 1.6, -0.4), right=(0, 0, 1), back=(1, 0, 0))
    assert pose.looked_at(head, edge_on) == 0.0


# ---- the link to SteamVR ------------------------------------------------

def test_no_steamvr_is_not_an_error_and_starts_nothing(steamvr):
    steamvr.running = False
    overlay = WristOverlay(steamvr)
    with pytest.raises(Lost):
        overlay.connect()
    assert not overlay.connected and steamvr.shutdowns == 0
    with pytest.raises(Lost):
        overlay.show(1.0)


def test_connect_joins_as_an_overlay_app_and_makes_one_hidden_overlay(steamvr):
    overlay = WristOverlay(steamvr)
    overlay.connect()
    overlay.connect()
    assert overlay.connected and steamvr.inits == 1 and len(steamvr.created) == 1
    assert not steamvr.shown
    assert steamvr.app_kind == openvr.VRApplication_Overlay
    assert Path(steamvr.manifest).is_file()


def test_an_overlay_left_by_a_crashed_copy_is_taken_over(steamvr):
    steamvr.key_in_use = True
    overlay = WristOverlay(steamvr)
    overlay.connect()
    overlay.close()
    assert steamvr.destroyed == [78]


def test_attach_image_and_show_reach_steamvr(steamvr):
    overlay = WristOverlay(steamvr)
    overlay.connect()
    place = pose.wrist_transform("left", 12, 6, 0, 0)
    overlay.attach(LEFT, place, 0.24)
    overlay.set_image(b"\x01\x02\x03\x04" * 6, 3, 2)
    overlay.show(0.5)
    device, sent = steamvr.attached[0]
    assert device == LEFT and sent == pytest.approx(place)
    assert steamvr.width == pytest.approx(0.24)
    assert steamvr.images == [(b"\x01\x02\x03\x04" * 6, 3, 2, 4)]
    assert steamvr.shown and steamvr.alpha == 0.5
    overlay.show(0.0)
    assert not steamvr.shown


def test_controller_numbers_and_poses(steamvr):
    overlay = WristOverlay(steamvr)
    overlay.connect()
    assert overlay.controller("left") == LEFT and overlay.controller("right") == RIGHT
    del steamvr.controllers[steamvr.TrackedControllerRole_RightHand]
    assert overlay.controller("right") is None
    head, hand = overlay.poses(0, LEFT)
    assert head[:, 3] == pytest.approx([0, 1.6, 0]) and hand is None


def test_steamvr_closing_lets_go_at_once(steamvr):
    overlay = WristOverlay(steamvr)
    overlay.connect()
    assert overlay.poll() is True
    steamvr.events = [openvr.VREvent_Quit]
    assert overlay.poll() is False
    assert not overlay.connected and steamvr.shutdowns == 1 and steamvr.destroyed == [77]


def test_a_failing_call_drops_the_link(steamvr):
    overlay = WristOverlay(steamvr)
    overlay.connect()
    steamvr.fail = "setOverlayTexture"
    with pytest.raises(Lost, match="setOverlayTexture failed"):
        overlay.set_image(b"\0" * 4, 1, 1)
    assert not overlay.connected and steamvr.shutdowns == 1


# ---- the panel ----------------------------------------------------------

def test_the_panel_is_a_see_through_picture_with_a_dark_plate(backend):
    panel = WristPanel(backend)
    backend.utterance.emit(Utterance(id=1, source="speaker", speaker=1, original="你好",
                                     translation="Xin chào", src_lang="zh", dst_lang="vi", final=True))
    picture = panel.image()
    assert (picture.width(), picture.height()) == SIZE
    assert len(rgba(picture)) == SIZE[0] * SIZE[1] * 4
    assert picture.pixelColor(0, 0).alpha() == 0                      # outside the round corner
    assert picture.pixelColor(SIZE[0] // 2, SIZE[1] // 2).alpha() >= 200


def test_the_panel_follows_the_backend(backend):
    panel = WristPanel(backend)
    changes = []
    panel.changed.connect(lambda: changes.append(1))
    backend.status_changed.emit(Status("ok", "Listening", ""))
    backend.status_changed.emit(Status("ok", "Listening", ""))          # nothing new to draw
    assert panel.status.text() == "Listening" and len(changes) == 1
    backend.utterance.emit(Utterance(id=5, source="mic", original="hello", final=True))
    assert len(panel.log.rows()) == 1 and len(changes) == 2


def test_no_background_leaves_only_the_letters(backend):
    panel = WristPanel(backend)
    panel.set_look(24, True, 0)
    assert panel.image().pixelColor(SIZE[0] // 2, SIZE[1] - 30).alpha() == 0


# ---- keeping it on the wrist --------------------------------------------

def test_without_steamvr_it_waits_and_does_not_try_to_join(wrist, steamvr):
    steamvr.running = False
    wrist.tick()
    wrist.clock.now += 60
    wrist.tick()
    assert wrist.state == display.WAITING and steamvr.inits == 0


def test_it_joins_when_steamvr_starts_and_puts_the_picture_on_the_left_wrist(wrist, steamvr):
    steamvr.running = False
    wrist.tick()
    steamvr.running = True
    wrist.tick()                                   # too soon after the last look
    assert steamvr.inits == 0
    wrist.clock.now += display.RETRY_S
    wrist.tick()
    assert wrist.state == display.ON
    assert steamvr.attached[0][0] == LEFT and steamvr.width == pytest.approx(0.24)
    assert len(steamvr.images) == 1 and steamvr.images[0][1:] == (*SIZE, 4)
    for _ in range(5):
        wrist.tick()
    assert steamvr.shown and steamvr.alpha == pytest.approx(0.95)
    assert len(steamvr.images) == 1 and len(steamvr.attached) == 1     # nothing sent twice


def test_a_change_is_sent_once_it_has_settled(wrist, steamvr, backend, app):
    wrist.tick()
    # (a status change, because the test platform has no fonts: new text would draw nothing)
    backend.status_changed.emit(Status("error", "VRChat is not running", ""))
    app.processEvents()
    wrist.tick()
    assert len(steamvr.images) == 1                # still arriving
    wrist.clock.now += display.SETTLE_S
    wrist.tick()
    assert len(steamvr.images) == 2


def test_controller_off_hides_the_panel_until_it_is_back(wrist, steamvr):
    wrist.tick()
    wrist.tick()
    del steamvr.controllers[steamvr.TrackedControllerRole_LeftHand]
    wrist.tick()
    assert wrist.state == display.NO_CONTROLLER and not steamvr.shown
    steamvr.controllers[steamvr.TrackedControllerRole_LeftHand] = 9     # back under a new number
    wrist.tick()
    assert wrist.state == display.ON and steamvr.attached[-1][0] == 9 and steamvr.shown


def test_look_only_shows_the_panel_while_the_wrist_is_turned_to_the_face(wrist, steamvr):
    wrist.settings.look_only = True
    # the left hand hangs at the side, pointing forward: the panel faces away to the left
    steamvr.room[LEFT] = room_pose((-0.3, 0.9, 0))
    for _ in range(6):
        wrist.tick()
    assert not steamvr.shown
    # raised like a watch: fingers to the right, back of the hand towards the eyes
    steamvr.room[LEFT] = room_pose((0, 1.6, -0.4), right=(0, 0, -1), up=(0, -1, 0), back=(-1, 0, 0))
    wrist.tick()
    assert steamvr.shown and 0 < steamvr.alpha < 0.95          # fading in
    for _ in range(6):
        wrist.tick()
    assert steamvr.alpha == pytest.approx(0.95)
    steamvr.room.pop(LEFT)                                     # tracking lost
    for _ in range(6):
        wrist.tick()
    assert not steamvr.shown


def test_hidden_wrist_defers_rendering_until_revealed(wrist, steamvr, backend, monkeypatch):
    wrist.settings.look_only = True
    steamvr.room[LEFT] = room_pose((-0.3, 0.9, 0))
    rendered = []
    original_image = wrist.panel.image

    def image(*args, **kwargs):
        rendered.append(1)
        return original_image(*args, **kwargs)

    monkeypatch.setattr(wrist.panel, "image", image)
    wrist.tick()
    backend.status_changed.emit(Status("error", "VRChat is not running", ""))
    wrist.clock.now += display.SETTLE_S
    wrist.tick()
    assert not rendered and not steamvr.images and wrist._dirty
    steamvr.room[LEFT] = room_pose((0, 1.6, -0.4), right=(0, 0, -1), up=(0, -1, 0), back=(-1, 0, 0))
    wrist.tick()
    assert len(rendered) == len(steamvr.images) == 1 and not wrist._dirty
    assert steamvr.shown
    steamvr.room[LEFT] = room_pose((-0.3, 0.9, 0))
    for _ in range(6):
        wrist.tick()
    backend.status_changed.emit(Status("ok", "Connected", ""))
    wrist.tick()
    assert len(rendered) == 1 and wrist._dirty
    steamvr.room[LEFT] = room_pose((0, 1.6, -0.4), right=(0, 0, -1), up=(0, -1, 0), back=(-1, 0, 0))
    wrist.tick()  # reveal must include new text even before its normal debounce expires
    assert len(rendered) == len(steamvr.images) == 2 and not wrist._dirty


def test_wrist_timer_slows_while_idle_and_resumes_after_reconnect(wrist, steamvr):
    steamvr.running = False
    wrist.start()
    try:
        wrist.tick()
        assert wrist._timer.interval() == display.IDLE_TICK_MS
        steamvr.running = True
        wrist.clock.now += display.RETRY_S
        wrist.tick()
        assert wrist.state == display.ON and wrist._timer.interval() == display.TICK_MS
        wrist.settings.enabled = False
        wrist.settings_changed()
        assert wrist.state == display.OFF and wrist._timer.interval() == display.IDLE_TICK_MS
        wrist.settings.enabled = True
        wrist.clock.now += display.RETRY_S
        wrist.settings_changed()
        assert wrist.state == display.ON and wrist._timer.interval() == display.TICK_MS
        steamvr.events = [openvr.VREvent_Quit]
        wrist.tick()
        assert wrist.state == display.WAITING and wrist._timer.interval() == display.IDLE_TICK_MS
        steamvr.running = True
        wrist.clock.now += display.AFTER_QUIT_S
        wrist.tick()
        assert wrist.state == display.ON and wrist._timer.interval() == display.TICK_MS
    finally:
        wrist.stop()
    assert not wrist._timer.isActive()


def test_the_right_hand_raised_like_a_watch_shows_it_too(wrist, steamvr):
    wrist.settings.look_only, wrist.settings.hand = True, "right"
    # fingers to the left, back of the hand towards the eyes, thumb towards the body
    steamvr.room[RIGHT] = room_pose((0, 1.6, -0.4), right=(0, 0, 1), up=(0, -1, 0), back=(1, 0, 0))
    for _ in range(6):
        wrist.tick()
    assert steamvr.attached[0][0] == RIGHT and steamvr.shown


def test_changed_settings_move_the_panel_and_are_saved(wrist, steamvr):
    wrist.tick()
    wrist.settings.hand, wrist.settings.width_cm, wrist.settings.along_cm = "right", 999, 20
    wrist.settings_changed()
    device, place = steamvr.attached[-1]
    assert device == RIGHT and place[2, 3] == pytest.approx(0.20)
    assert steamvr.width == pytest.approx(config.WIDTH_RANGE[1] / 100)     # 999 was cut to the limit
    assert wrist.saved[-1].hand == "right"


def test_switched_off_lets_go_of_steamvr(wrist, steamvr):
    wrist.tick()
    wrist.settings.enabled = False
    wrist.settings_changed()
    assert wrist.state == display.OFF and steamvr.shutdowns == 1
    wrist.settings.enabled = True
    wrist.clock.now += display.RETRY_S
    wrist.settings_changed()
    assert wrist.state == display.ON and steamvr.inits == 2 and len(steamvr.images) == 2


def test_steamvr_closing_is_left_alone_for_a_while(wrist, steamvr):
    wrist.tick()
    steamvr.events = [openvr.VREvent_Quit]
    wrist.tick()
    assert wrist.state == display.WAITING and steamvr.shutdowns == 1
    steamvr.running = True                         # still closing down, or already started again
    wrist.clock.now += display.RETRY_S
    wrist.tick()
    assert steamvr.inits == 1
    wrist.clock.now += display.AFTER_QUIT_S
    wrist.tick()
    assert steamvr.inits == 2 and wrist.state == display.ON


def test_a_broken_link_says_why_and_is_made_again(wrist, steamvr):
    steamvr.fail = "setOverlayTexture"
    wrist.tick()
    assert wrist.state == display.WAITING and "setOverlayTexture failed" in wrist.problem
    steamvr.fail = ""
    wrist.clock.now += display.RETRY_S
    wrist.tick()
    assert wrist.state == display.ON and wrist.problem == ""


def test_the_panel_follows_the_windows_settings(backend, steamvr):
    window = Settings(show_original=True, mic_on=True, ui_lang="en")
    panel = WristPanel(backend)
    wrist = WristDisplay(panel, VrSettings(font_px=30), window_settings=lambda: window,
                         overlay=WristOverlay(steamvr), save=lambda s: None, running=lambda: False)
    wrist.tick()
    assert panel.log._look == (30, True, False)
    window.show_original, window.ui_lang = False, "zh"
    backend.status_changed.emit(Status("ok", "Settings", ""))
    from ui import i18n
    i18n.set_lang("zh")                             # the window does this when its language changes
    try:
        wrist.tick()
        assert panel.log._look == (30, False, False)
        assert panel.status.text() == "设置"        # retranslated with the window
    finally:
        i18n.set_lang("en")


# ---- settings -----------------------------------------------------------

def test_settings_round_trip_and_bad_files(tmp_path):
    path = tmp_path / "vr.json"
    assert config.load(path) == VrSettings()
    config.save(VrSettings(hand="right", width_cm=30, look_only=False), path)
    assert config.load(path) == VrSettings(hand="right", width_cm=30, look_only=False)
    config.save(VrSettings(yaw_deg=65, roll_deg=-130), path)
    assert config.load(path) == VrSettings(yaw_deg=65, roll_deg=-130)
    path.write_text('{"yaw_deg": 999, "roll_deg": -999}', encoding="utf-8")
    assert (config.load(path).yaw_deg, config.load(path).roll_deg) == (180, -180)
    path.write_text('{"hand": "foot", "width_cm": 5000, "opacity": "full", "tilt_deg": -400}', encoding="utf-8")
    loaded = config.load(path)
    assert loaded.yaw_deg == loaded.roll_deg == 0  # older settings keep their placement
    assert (loaded.hand, loaded.width_cm, loaded.opacity, loaded.tilt_deg) == ("left", 50, 95, -90)
    path.write_text("not json", encoding="utf-8")
    assert config.load(path) == VrSettings()


def test_the_dialog_changes_saves_and_resets(wrist, steamvr):
    wrist.tick()
    dialog = VrDialog(wrist)
    assert dialog._sliders["width_cm"][0].value() == 24 and dialog.hand.currentData() == "left"
    assert wrist.saved == []                        # opening it changes nothing
    dialog._sliders["tilt_deg"][0].setValue(40)
    dialog._sliders["along_cm"][0].setValue(20)
    dialog._switches["look_only"].setChecked(True)
    assert (wrist.settings.tilt_deg, wrist.settings.along_cm, wrist.settings.look_only) == (40, 20, True)
    assert wrist.saved[-1].tilt_deg == 40 and steamvr.attached[-1][1][2, 3] == pytest.approx(0.20)
    dialog.reset_place()
    assert (wrist.settings.tilt_deg, wrist.settings.along_cm) == (0, 12)
    assert dialog._sliders["tilt_deg"][0].value() == 0
    assert wrist.settings.look_only is True         # only the place is reset
    assert dialog.preview.scene().items()
    assert dialog.arm.pixmap() is not None and not dialog.arm.pixmap().isNull()
    assert dialog.state.text() == display.ON


@pytest.mark.parametrize("language", ["en", "zh", "vi"])
def test_wrist_settings_minimum_size_keeps_controls_inside_viewport(wrist, app, language):
    from PySide6.QtCore import QPoint, QRect
    from PySide6.QtWidgets import QScrollArea
    from ui import i18n
    i18n.set_lang(language)
    dialog = VrDialog(wrist)
    try:
        dialog.show()
        dialog.resize(1, 1)
        app.processEvents()
        assert dialog.size() == dialog.minimumSize()
        assert dialog.height() >= 600
        scroll = dialog.findChild(QScrollArea, "page")
        viewport = scroll.viewport()
        assert scroll.widget().width() <= viewport.width()
        controls = [dialog.preview, dialog.hand, *dialog._switches.values()]
        for slider, value, _unit in dialog._sliders.values():
            slider.setValue(slider.maximum())
            controls.extend((slider, value))
        for control in controls:
            scroll.ensureWidgetVisible(control)
            app.processEvents()
            rect = QRect(control.mapTo(viewport, QPoint()), control.size())
            assert viewport.rect().contains(rect), (language, control, rect, viewport.rect())
        assert not scroll.horizontalScrollBar().isVisible()
        minimum = dialog.minimumSize()
        dialog.resize(minimum.width() + 200, minimum.height() + 100)
        app.processEvents()
        assert dialog.width() > minimum.width() and dialog.height() > minimum.height()
    finally:
        dialog.close()
        i18n.set_lang("en")


def test_previews_render_while_settings_are_still_changing(wrist, app, monkeypatch):
    from PySide6.QtTest import QTest
    dialog = VrDialog(wrist)
    frames = []
    original = dialog.arm.set_scene

    def rendered(settings, image):
        original(settings, image)
        frames.append(settings.yaw_deg)

    try:
        dialog.show()
        app.processEvents()
        before = dialog.arm.pixmap().toImage().copy()
        monkeypatch.setattr(dialog.arm, "set_scene", rendered)
        for value in range(5, 41, 5):
            dialog._sliders["yaw_deg"][0].setValue(value)
            dialog._sliders["opacity"][0].setValue(100 - value)
            dialog._sliders["font_px"][0].setValue(20 + value // 5)
            dialog._sliders["backdrop"][0].setValue(100 - value)
            QTest.qWait(25)  # keep changing faster than the old 150 ms debounce
        assert len(set(frames)) >= 2 and any(value < 40 for value in frames)
        QTest.qWait(50)
        assert frames[-1] == 40
        assert dialog.preview_panel.log._look[0] == 28
        assert dialog.preview_panel._backdrop == 60
        assert dialog._preview_proxy.opacity() == pytest.approx(0.6)
        assert dialog.arm.pixmap().toImage() != before
    finally:
        dialog.close()


def test_wrist_appearance_settings_upload_without_waiting_for_text_debounce(wrist, steamvr, backend, app):
    backend.utterance.emit(Utterance(1, "speaker", original="Live appearance settings", final=True))
    app.processEvents()
    wrist.tick()
    initial = len(steamvr.images)
    for font in (26, 28, 30):
        wrist.settings.font_px = font
        wrist.settings_changed()
    # The fake clock has not advanced: these must bypass subtitle settling.
    assert len(steamvr.images) == initial + 3
    assert len(set(steamvr.texture_ids[77])) == 1 and not steamvr.destroyed


def test_arm_preview_orbits_and_follows_place(wrist):
    from vr.arm_preview import ArmPreview, draw

    wrist.tick()
    before = draw(wrist.settings, wrist.panel.image(), yaw_deg=28, pitch_deg=18)
    moved = draw(VrSettings(hand="right", along_cm=20, tilt_deg=40),
                 wrist.panel.image(), yaw_deg=28, pitch_deg=18)
    assert before != moved

    view = ArmPreview()
    view.set_scene(wrist.settings, wrist.panel.image())
    first = view.pixmap().toImage().copy()
    view._yaw += 45
    view.redraw()
    assert view.pixmap().toImage() != first


@pytest.mark.parametrize("hand", ["left", "right"])
def test_preview_hand_faces_dorsal_side_toward_overlay(hand):
    from vr.arm_preview import mesh_transform, watch_pose
    model = mesh_transform(hand)
    panel = pose.wrist_transform(hand, 12, 6, 0, 0)
    # Anatomical landmarks in the asset: elbow +Y, thumb +X, back of hand +Z.
    assert model[:, 1] == pytest.approx([0, 0, 1])
    assert model[:, 0] == pytest.approx([0, -1, 0])
    assert model[:, 2] == pytest.approx(panel[:, 2])
    assert np.dot(panel[:, 3] - model[:, 3], model[:, 2]) > 0
    left, right = mesh_transform("left"), mesh_transform("right")
    assert np.diag([-1, 1, 1]) @ left == pytest.approx(right)
    world_model = pose.compose(watch_pose(hand), model)
    world_panel = pose.compose(watch_pose(hand), panel)
    assert np.dot(world_panel[:, 3] - world_model[:, 3], world_model[:, 2]) > 0


def test_preview_wheel_zooms_without_changing_wrist_settings(wrist, app):
    from dataclasses import replace
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from vr.arm_preview import ArmPreview, DEFAULT_DISTANCE, ZOOM_RANGE

    view = ArmPreview()
    view.resize(380, 340)
    view.set_scene(wrist.settings, wrist.panel.image())
    original_settings = replace(wrist.settings)
    before = view.pixmap().toImage().copy()

    def wheel(angle=0, pixels=0):
        event = QWheelEvent(QPointF(150, 150), QPointF(150, 150), QPoint(0, pixels),
                            QPoint(0, angle), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
        app.sendEvent(view, event)
        assert event.isAccepted()

    wheel(120)
    assert view._distance < DEFAULT_DISTANCE
    assert view.pixmap().toImage() != before
    closer = view._distance
    view.set_scene(wrist.settings, wrist.panel.image())
    assert view._distance == closer  # subtitle refreshes keep the chosen zoom
    wheel(-120)
    assert view._distance == pytest.approx(DEFAULT_DISTANCE)
    wheel(pixels=60)
    assert view._distance < DEFAULT_DISTANCE
    wheel(12000)
    assert view._distance == ZOOM_RANGE[0]
    for _ in range(3):
        wheel(-12000)
    assert view._distance == ZOOM_RANGE[1]
    assert wrist.settings == original_settings and wrist.saved == []


def test_the_window_gets_a_vr_button_before_the_gear(app, wrist):
    window = MainWindow(Backend(), Settings(), save=lambda s: None)
    row = window.title_buttons
    before = row.count()
    button = add_vr_button(window, wrist)
    assert row.count() == before + 1 and row.indexOf(button) == before - 4
    assert button.text() == "VR" and display.OFF in button.toolTip()
    window.show()
    app.processEvents()
    assert button.width() >= button.fontMetrics().horizontalAdvance("VR") + 10
    wrist.tick()
    assert display.ON in button.toolTip()
    window.close()


def test_normal_app_starts_and_stops_wrist_without_replacing_startup(app, backend, monkeypatch):
    from PySide6.QtWidgets import QToolButton
    from ui import main as ui_main
    windows, calls = [], []

    def make_window(backend, settings):
        window = MainWindow(backend, settings, save=lambda s: None)
        windows.append(window)
        return window

    def event_loop():
        window = windows[0]
        wrist = window.findChild(WristDisplay)
        assert wrist is not None and wrist._timer.isActive()
        wrist.tick()
        assert wrist.state == display.OFF and not wrist.overlay.connected
        button = next(b for b in window.findChildren(QToolButton) if b.text() == "VR")
        button.click()
        dialog = window.findChild(VrDialog)
        assert dialog.isVisible() and dialog.display is wrist
        dialog.close()
        assert calls == ["backend started", "updater"]
        return 7

    monkeypatch.setattr(ui_main, "MainWindow", make_window)
    monkeypatch.setattr(MainWindow, "show_update_notice", lambda self: None)
    monkeypatch.setattr(ui_main.config, "load", lambda: Settings())
    monkeypatch.setattr(config, "load", lambda: VrSettings(enabled=False))
    monkeypatch.setattr(ui_main, "look_for_update", lambda b: calls.append("updater"))
    monkeypatch.setattr(backend, "start", lambda: calls.append("backend started"))
    monkeypatch.setattr(backend, "stop", lambda: calls.append("backend stopped"))
    monkeypatch.setattr(app, "exec", event_loop)
    try:
        assert ui_main.run(backend) == 7
        wrist = windows[0].findChild(WristDisplay)
        assert not wrist._timer.isActive() and not wrist.overlay.connected
        assert calls == ["backend started", "updater", "backend stopped"]
    finally:
        for window in windows:
            wrist = window.findChild(WristDisplay)
            if wrist is not None:
                app.aboutToQuit.disconnect(wrist.stop)
                wrist.stop()
                wrist.panel.close()
                wrist.panel.deleteLater()
            window.close()
            window.deleteLater()


def test_missing_openvr_keeps_desktop_and_wrist_log_usable(backend, monkeypatch):
    import builtins
    original_import = builtins.__import__

    def without_openvr(name, *args, **kwargs):
        if name == "openvr":
            raise ImportError("missing OpenVR DLL")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_openvr)
    window = MainWindow(backend, Settings(), save=lambda s: None)
    wrist = WristDisplay(WristPanel(backend), VrSettings(), running=lambda: True, save=lambda s: None)
    try:
        wrist.tick()
        assert wrist.state == display.WAITING and "missing OpenVR DLL" in wrist.problem
        backend.utterance.emit(Utterance(1, "speaker", original="Still listening", final=True))
        assert len(window.log.rows()) == len(wrist.panel.log.rows()) == 1
        assert not wrist.overlay.connected
    finally:
        wrist.stop()
        wrist.panel.close()
        window.close()


def test_wrist_and_desktop_share_progressive_multilingual_subtitles(backend, wrist):
    from dataclasses import replace
    from PySide6.QtGui import QTextDocument
    window = MainWindow(backend, Settings(), save=lambda s: None)
    utterance = Utterance(101, "speaker", original="Hello 你好", src_lang="en", dst_lang="en",
                          panel_targets=("en", "vi", "zh"),
                          panel_translations=(("en", "Hello, hello"),))
    try:
        backend.utterance.emit(utterance)
        row = wrist.panel.log.rows()[0]
        assert "Hello, hello" in row.translation.text()
        final = replace(utterance, final=True, panel_translations=(
            ("en", "Hello, hello"), ("vi", "Xin chào"), ("zh", "你好")))
        backend.utterance.emit(final)
        assert wrist.panel.log.rows() == [row]
        desktop_row = window.log.rows()[0]
        for field, text in (("translation", "Hello, hello"), ("translation2", "Xin chào"),
                            ("translation3", "你好")):
            label = getattr(row, field)
            assert text in label.text() and not label.isHidden()
            wrist_text, desktop_text = QTextDocument(), QTextDocument()
            wrist_text.setHtml(label.text())
            desktop_text.setHtml(getattr(desktop_row, field).text())
            assert wrist_text.toPlainText() == desktop_text.toPlainText()
    finally:
        window.close()


@pytest.mark.parametrize("hand", ["left", "right"])
def test_pointer_ray_hits_the_visible_front_and_rejects_misses(hand):
    panel = pose.wrist_transform(hand, 12, 6, 0, 35)
    aim = pose.compose(panel, room_pose((0.03, 0.02, 0.3)))
    assert pose.pointer_hit(aim, panel, 0.24, 2 / 3) == pytest.approx((0.625, 0.375))
    for local in (room_pose((0, 0, -0.3)), room_pose((0.2, 0, 0.3)),
                  room_pose((0, 0, 3)), room_pose((0, 0, 0.3), right=(0, 0, -1), back=(1, 0, 0))):
        assert pose.pointer_hit(pose.compose(panel, local), panel, 0.24, 2 / 3) is None


def aim_at_button(wrist, steamvr, button, point=None):
    """Raise the wrist and aim the other controller at an actual laid-out button."""
    from vr.arm_preview import watch_pose
    from PySide6.QtCore import QPoint
    device = LEFT if wrist.settings.hand == "left" else RIGHT
    other = RIGHT if device == LEFT else LEFT
    steamvr.room[device] = watch_pose(wrist.settings.hand)
    transform = pose.wrist_transform(wrist.settings.hand, wrist.settings.along_cm,
                                     wrist.settings.out_cm, wrist.settings.up_cm, wrist.settings.tilt_deg,
                                     wrist.settings.yaw_deg, wrist.settings.roll_deg)
    world = pose.compose(steamvr.room[device], transform)
    steamvr.room[0] = pose.compose(world, room_pose((0, 0, 0.4)))
    wrist.panel.layout().activate()
    point = button.mapTo(wrist.panel, point if point is not None else QPoint(button.width() // 2, button.height() // 2))
    local = room_pose(((point.x() / SIZE[0] - 0.5) * wrist.settings.width_cm / 100,
                       (0.5 - point.y() / SIZE[1]) * wrist.settings.width_cm / 100 * SIZE[1] / SIZE[0], 0.3))
    steamvr.aims[other] = pose.compose(world, local)
    return other


@pytest.mark.parametrize("hand", ["left", "right"])
def test_opposite_trigger_updates_shared_capture_settings_once(wrist, steamvr, backend, hand, app):
    from dataclasses import replace
    saved, applied = [], []
    window = MainWindow(backend, Settings(), save=lambda settings: saved.append(replace(settings)))
    backend.apply_settings = lambda settings: applied.append(replace(settings))
    bind_wrist_controls(window, wrist.panel)
    wrist._window_settings = lambda: window.settings
    wrist.settings.hand = hand
    other = aim_at_button(wrist, steamvr, wrist.panel.mic)
    for _ in range(5):
        wrist.tick()
    steamvr.triggers[other] = True
    for _ in range(5):
        wrist.tick()
    assert saved == []  # selection happens on release
    steamvr.triggers[other] = False
    wrist.tick()
    assert len(saved) == len(applied) == 1
    assert not saved[-1].mic_on and saved[-1].subtitles_on
    assert wrist.panel._switches == (False, True)
    assert steamvr.input_sources and set(steamvr.input_sources) == {other}
    for button in (wrist.panel.speaker,):
        app.processEvents()
        aim_at_button(wrist, steamvr, button)
        wrist.tick()
        steamvr.triggers[other] = True
        wrist.tick()
        steamvr.triggers[other] = False
        wrist.tick()
    assert not window.settings.mic_on and not window.settings.subtitles_on
    assert len(saved) == len(applied) == 2
    window.close()


def test_trigger_held_while_entering_or_reconnecting_cannot_click(wrist, steamvr):
    selected = []
    wrist.panel.toggle_requested.connect(selected.append)
    other = aim_at_button(wrist, steamvr, wrist.panel.mic)
    steamvr.triggers[other] = True
    for _ in range(5):
        wrist.tick()
    steamvr.triggers[other] = False
    wrist.tick()
    assert not selected
    steamvr.triggers[other] = True
    wrist.tick()
    steamvr.fail = "pollNextEvent"
    wrist.tick()
    assert wrist.panel._pointer is None
    steamvr.fail = ""
    wrist.clock.now += display.RETRY_S
    for _ in range(5):
        wrist.tick()
    steamvr.triggers[other] = False
    wrist.tick()
    assert not selected


@pytest.mark.parametrize("hand", ["left", "right"])
def test_rotation_controls_update_preview_attachment_clicks_and_reset(wrist, steamvr, hand):
    wrist.settings.hand = hand
    wrist.tick()
    dialog = VrDialog(wrist)
    preview = dialog.arm.pixmap().toImage().copy()
    center = steamvr.attached[-1][1][:, 3].copy()
    for name, angle in (("yaw_deg", 25), ("roll_deg", 90)):
        before = len(steamvr.attached)
        dialog._sliders[name][0].setValue(angle)
        assert len(steamvr.attached) == before + 1
        assert getattr(wrist.saved[-1], name) == angle
    dialog.show_preview()
    assert dialog.arm.pixmap().toImage() != preview
    assert steamvr.attached[-1][1][:, 3] == pytest.approx(center)
    other = aim_at_button(wrist, steamvr, wrist.panel.mic)
    selected = []
    wrist.panel.toggle_requested.connect(selected.append)
    for _ in range(5):
        wrist.tick()
    steamvr.triggers[other] = True
    wrist.tick()
    steamvr.triggers[other] = False
    wrist.tick()
    assert selected == ["mic_on"] and steamvr.cursor_shown
    dialog.reset_place()
    assert wrist.settings.yaw_deg == wrist.settings.roll_deg == 0
    assert dialog._sliders["yaw_deg"][0].value() == dialog._sliders["roll_deg"][0].value() == 0
    assert steamvr.attached[-1][1] == pytest.approx(pose.wrist_transform(hand, 12, 6, 0, 0))
    dialog.close()


def test_looking_away_or_losing_input_cancels_press_even_with_always_visible_panel(wrist, steamvr):
    selected = []
    wrist.panel.toggle_requested.connect(selected.append)
    other = aim_at_button(wrist, steamvr, wrist.panel.mic)
    for _ in range(5):
        wrist.tick()
    steamvr.triggers[other] = True
    wrist.tick()
    head = steamvr.room.pop(0)
    wrist.tick()
    steamvr.triggers[other] = False
    steamvr.room[0] = head
    wrist.tick()
    assert not selected
    steamvr.triggers[other] = True
    wrist.tick()
    steamvr.input_active = False
    wrist.tick()
    assert wrist.panel._pointer is None
    steamvr.input_active = True
    steamvr.triggers[other] = False
    wrist.tick()
    assert not selected


def test_pointer_moves_without_replacing_subtitle_texture_and_input_failure_preserves_overlay(wrist, steamvr):
    aim_at_button(wrist, steamvr, wrist.panel.mic)
    for _ in range(5):
        wrist.tick()
    count = len(steamvr.images)
    cursor_before = steamvr.cursor_attached[-1][1].copy()
    aim_at_button(wrist, steamvr, wrist.panel.speaker)
    wrist.tick()  # fake clock hasn't advanced; the cursor must still update
    assert len(steamvr.images) == count
    assert len(steamvr.cursor_images) == 1 and steamvr.cursor_shown
    assert not np.array_equal(steamvr.cursor_attached[-1][1], cursor_before)
    steamvr.fail = "getDigitalActionData"
    wrist.tick()
    assert wrist.state == display.ON and wrist.overlay.connected and steamvr.shown
    assert "getDigitalActionData" in wrist.problem
    assert wrist.panel._pointer is None
    assert not steamvr.cursor_shown
    steamvr.fail = ""
    wrist.tick()
    assert wrist.problem == ""


def test_scroll_and_mute_updates_keep_the_same_visible_gpu_texture(wrist, steamvr, backend, app):
    window = MainWindow(backend, Settings(), save=lambda s: None)
    bind_wrist_controls(window, wrist.panel)
    wrist._window_settings = lambda: window.settings
    try:
        for number in range(30):
            backend.utterance.emit(Utterance(number, "speaker", original="Scroll this conversation " * 8, final=True))
        app.processEvents()
        app.processEvents()
        other = aim_at_button(wrist, steamvr, wrist.panel.mic)
        for _ in range(5):
            wrist.tick()
        initial = len(steamvr.images)
        bar = wrist.panel.log.verticalScrollBar()
        for direction in (1, -1) * 5:
            before = bar.value()
            steamvr.scrolls[other] = direction
            wrist.tick()
            assert bar.value() != before
            assert steamvr.shown and steamvr.alpha == pytest.approx(wrist.settings.opacity / 100)
        assert len(steamvr.images) == initial + 10
        steamvr.scrolls[other] = 0
        for button in (wrist.panel.mic, wrist.panel.speaker) * 2:
            aim_at_button(wrist, steamvr, button)
            wrist.tick()
            steamvr.triggers[other] = True
            wrist.tick()
            steamvr.triggers[other] = False
            wrist.tick()
            assert steamvr.shown
        assert window.settings.mic_on and window.settings.subtitles_on
        assert len(set(steamvr.texture_ids[77])) == len(set(steamvr.texture_ids[79])) == 1
        assert len(steamvr.created) == 2 and not steamvr.destroyed and not steamvr.hidden
    finally:
        window.close()


def test_gpu_failure_releases_resources_and_reconnects_with_fresh_textures(wrist, steamvr, monkeypatch):
    from vr.texture import TextureError
    aim_at_button(wrist, steamvr, wrist.panel.mic)
    for _ in range(5):
        wrist.tick()
    previous = wrist.overlay._textures

    def fail(*args):
        raise TextureError("graphics context lost")

    monkeypatch.setattr(previous, "submit", fail)
    wrist.panel.mic.setDown(True)
    wrist._interaction_changed()
    wrist.tick()
    assert wrist.state == display.WAITING and "graphics context lost" in wrist.problem
    assert previous.closed and wrist.overlay._textures is None
    assert set(steamvr.destroyed) == {77, 79}
    wrist.clock.now += display.RETRY_S
    wrist.tick()
    assert wrist.state == display.ON and wrist.problem == ""
    assert wrist.overlay._textures is not previous
    current = wrist.overlay._textures
    wrist.stop()
    assert current.closed


@pytest.mark.parametrize("hand", ["left", "right"])
def test_cursor_follows_panel_size_pose_and_is_cleaned_up(wrist, steamvr, hand):
    wrist.settings.hand = hand
    other = aim_at_button(wrist, steamvr, wrist.panel.mic)
    for _ in range(5):
        wrist.tick()
    from vr.panel import CURSOR_SIZE
    assert steamvr.cursor_width == pytest.approx(steamvr.width * CURSOR_SIZE / SIZE[0])
    device, panel_transform = steamvr.attached[-1]
    cursor_device, cursor_transform = steamvr.cursor_attached[-1]
    uv, _ = wrist.panel.pointer
    local = panel_transform[:, :3].T @ (cursor_transform[:, 3] - panel_transform[:, 3])
    assert cursor_device == device
    assert local == pytest.approx([(uv[0] - 0.5) * steamvr.width,
                                  (0.5 - uv[1]) * steamvr.width * SIZE[1] / SIZE[0], 0.001], abs=1e-7)
    count = len(steamvr.images)
    steamvr.triggers[other] = True
    wrist.tick()
    assert wrist.panel.mic.isDown() and len(steamvr.images) == count + 1
    assert len(steamvr.cursor_images) == 2
    steamvr.room.pop(device)
    wrist.tick()
    assert not steamvr.cursor_shown and not wrist.panel.mic.isDown()
    wrist.stop()
    assert set(steamvr.destroyed) == {77, 79}


def test_gaze_jitter_keeps_panel_and_press_stable_but_looking_away_cancels(wrist, steamvr, monkeypatch):
    wrist.settings.look_only = True
    other = aim_at_button(wrist, steamvr, wrist.panel.mic)
    for _ in range(5):
        wrist.tick()
    selected = []
    wrist.panel.toggle_requested.connect(selected.append)
    steamvr.triggers[other] = True
    wrist.tick()
    for gaze in (0.49, 0.51, 0.45, 0.52, 0.31):
        monkeypatch.setattr(pose, "looked_at", lambda *args: gaze)
        wrist.tick()
        assert steamvr.alpha == pytest.approx(wrist.settings.opacity / 100)
        assert wrist.panel.mic.isDown() and steamvr.cursor_shown
    monkeypatch.setattr(pose, "looked_at", lambda *args: 0.0)
    wrist.tick()
    assert not wrist.panel.mic.isDown() and not steamvr.cursor_shown
    steamvr.triggers[other] = False
    for _ in range(5):
        wrist.tick()
    assert not steamvr.shown and not selected
    monkeypatch.setattr(pose, "looked_at", lambda *args: 0.49)
    wrist.tick()
    assert not steamvr.shown and not steamvr.cursor_shown


def test_wrist_controls_follow_desktop_language_and_scroll_behavior(wrist, backend, app):
    from ui import i18n
    from PySide6.QtCore import QPoint
    saved = []
    window = MainWindow(backend, Settings(my_lang="en", their_lang="vi", their_lang2=""), save=lambda s: saved.append(s.ui_lang))
    bind_wrist_controls(window, wrist.panel)
    wrist._window_settings = lambda: window.settings

    def click(button):
        app.processEvents()
        point = button.mapTo(wrist.panel, QPoint(button.width() // 2, button.height() // 2))
        uv = point.x() / SIZE[0], point.y() / SIZE[1]
        wrist.panel.point(uv)
        wrist.panel.point(uv, True)
        wrist.panel.point(uv, False)
        wrist.tick()

    try:
        wrist.tick()
        window._ui_lang_picked("vi")
        wrist.tick()
        assert window.settings.ui_lang == i18n.lang() == "vi" and saved[-1] == "vi"
        assert wrist.panel.speaker.toolTip() == i18n.tr("Other players → subtitles")
        click(wrist.panel.speaker)
        assert not window.settings.subtitles_on and window.settings.mic_on
        for number in range(30):
            backend.utterance.emit(Utterance(number, "speaker", original="Older conversation " * 10, final=True))
        app.processEvents()
        app.processEvents()
        bar = wrist.panel.log.verticalScrollBar()
        assert bar.maximum() > 0
        wrist.panel.scroll(-wrist.panel.log.viewport().height() // 2)
        previous = bar.value()
        assert previous < bar.maximum() and not wrist.panel.log._stick
        backend.utterance.emit(Utterance(100, "speaker", original="New line", final=True))
        app.processEvents()
        assert bar.value() == previous
        wrist.panel.scroll(bar.maximum())
        assert bar.value() == bar.maximum() and wrist.panel.log._stick
    finally:
        i18n.set_lang("en")
        window.close()


@pytest.mark.parametrize("language", ["en", "zh", "vi"])
def test_inline_wrist_demo_clicks_and_scrolls_without_changing_live_capture(wrist, app, language):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton, QStyle, QStyleOptionSlider, QToolButton
    from ui import i18n
    i18n.set_lang(language)
    live_changes = []
    wrist.panel.toggle_requested.connect(live_changes.append)
    live_rows = list(wrist.panel.log.rows())
    dialog = VrDialog(wrist)
    try:
        dialog.show()
        app.processEvents()
        app.processEvents()
        panel = dialog.preview_panel
        viewport = dialog.preview.viewport()

        def position(widget, point):
            return dialog.preview.mapFromScene(panel.graphicsProxyWidget().mapToScene(
                QPointF(widget.mapTo(panel, point))))

        assert dialog.preview.isVisible() and panel.isVisible()
        assert len(panel.log.rows()) == 10
        assert panel.status.text() == i18n.tr("Demo")
        assert all(button.text() != i18n.tr("Try wrist controls")
                   for button in dialog.findChildren(QPushButton))
        assert {button for button in panel.findChildren(QToolButton) if button.isVisible()} == {
            panel.my_lang, panel.swap, panel.their_lang, panel.mic, panel.speaker}
        assert panel.my_lang.text().startswith(i18n.tr("I") + " ")
        assert panel.their_lang.text().startswith(i18n.tr("They") + " ")
        original_languages = wrist.panel._languages
        for button in (panel.my_lang, panel.language_choices["zh"], panel.language_choices["vi"],
                       panel.language_done, panel.swap):
            QTest.mouseClick(viewport, Qt.LeftButton, pos=position(button, button.rect().center()))
            app.processEvents()
        assert panel._languages == (["en"], ["zh"])
        for button in (panel.their_lang, panel.language_choices["ja"]):
            QTest.mouseClick(viewport, Qt.LeftButton, pos=position(button, button.rect().center()))
            app.processEvents()
        assert panel._languages == (["en"], ["zh", "ja"])
        assert panel.language_choices["zh"].isChecked() and panel.language_choices["ja"].isChecked()
        assert "ZH + JA" in panel.their_lang.text() and panel.swap.isEnabled()
        QTest.mouseClick(viewport, Qt.LeftButton, pos=position(panel.language_done, panel.language_done.rect().center()))
        app.processEvents()
        assert not panel.language_menu.isVisible()
        assert wrist.panel._languages == original_languages and not wrist.saved
        for button in (panel.mic, panel.speaker):
            QTest.mouseClick(viewport, Qt.LeftButton, pos=position(button, button.rect().center()))
        assert panel._switches == (False, False)
        assert wrist.panel._switches == (True, True) and not live_changes and not wrist.saved
        assert wrist.panel.log.rows() == live_rows
        assert not wrist.overlay.connected
        bar = panel.log.verticalScrollBar()
        assert bar.maximum() > 0 and bar.isVisible()
        bar.setValue(bar.maximum())
        option = QStyleOptionSlider()
        bar.initStyleOption(option)
        handle = bar.style().subControlRect(
            QStyle.CC_ScrollBar, option, QStyle.SC_ScrollBarSlider, bar)
        QTest.mousePress(viewport, Qt.LeftButton, pos=position(bar, handle.center()))
        QTest.mouseMove(viewport, position(bar, QPoint(handle.center().x(), 4)))
        QTest.mouseRelease(viewport, Qt.LeftButton, pos=position(bar, QPoint(handle.center().x(), 4)))
        assert bar.value() < bar.maximum() and not panel.log._stick
        bar.setValue(bar.maximum())
        point = QPointF(position(panel.log.viewport(), panel.log.viewport().rect().center()))
        wheel = QWheelEvent(point, QPointF(viewport.mapToGlobal(point.toPoint())),
                            QPoint(), QPoint(0, 120), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
        app.sendEvent(viewport, wheel)
        assert bar.value() < bar.maximum() and not panel.log._stick
        dialog.show_preview()
        assert dialog.arm._panel == panel.image()
        dialog._sliders["font_px"][0].setValue(28)
        dialog._sliders["backdrop"][0].setValue(60)
        dialog._sliders["opacity"][0].setValue(70)
        dialog.show_preview()
        assert panel.log._look[0] == 28 and panel._backdrop == 60
        assert panel.graphicsProxyWidget().opacity() == pytest.approx(0.7)
        assert dialog.arm._panel == panel.image()
        dialog.close()
        dialog.show()
        assert dialog.preview_panel is panel and panel.isVisible()
    finally:
        dialog.close()
        i18n.set_lang("en")


def test_bundled_hand_is_connected_and_missing_asset_keeps_preview_working(app, monkeypatch, tmp_path):
    from vr import arm_preview
    mesh = arm_preview.hand_mesh()
    vertices, faces, normals = mesh
    assert len(faces) < 10000 and len(vertices) < len(faces)
    # The previous sparse asset discarded triangles; connected triangles share edges.
    edges = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    assert np.mean(counts == 2) > 0.9
    assert np.linalg.norm(normals, axis=1) == pytest.approx(np.ones(len(faces)), abs=1e-5)
    monkeypatch.setattr(arm_preview, "MESH_PATH", tmp_path / "missing.npz")
    arm_preview.hand_mesh.cache_clear()
    try:
        assert arm_preview.hand_mesh() is None
        preview = arm_preview.ArmPreview()
        assert not preview.pixmap().isNull()
    finally:
        arm_preview.hand_mesh.cache_clear()


def test_hand_reduction_retains_surface_and_rejects_nonfinite_input():
    from tools.prepare_hand import reduce_mesh
    vertices = np.array([[0., 0, 0], [1, 0, 0], [0, 2, 0], [0, 0, 1]])
    faces = np.array([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]])
    reduced, triangles, normals = reduce_mesh(vertices, faces)
    assert len(triangles) == 4 and np.isfinite(normals).all()
    assert (reduced.max(axis=0) - reduced.min(axis=0)).max() == pytest.approx(0.3)
    vertices[0, 0] = np.nan
    with pytest.raises(ValueError):
        reduce_mesh(vertices, faces)


def test_bundled_input_bindings_cover_both_hands():
    import json
    folder = Path(__file__).resolve().parent.parent / "assets/vr"
    manifest = json.loads((folder / "actions.json").read_text(encoding="utf-8"))
    actions = {entry["name"] for entry in manifest["actions"]}
    for binding in manifest["default_bindings"]:
        data = json.loads((folder / binding["binding_url"]).read_text(encoding="utf-8"))
        assert binding["controller_type"] == data["controller_type"]
        for hand in ("left", "right"):
            outputs = set()
            for group in data["bindings"].values():
                outputs.update(pose["output"] for pose in group["poses"] if f"/{hand}/" in pose["path"])
                for source in group["sources"]:
                    if f"/{hand}/" in source["path"]:
                        outputs.update(item["output"] for item in source["inputs"].values())
            assert outputs == actions


@pytest.mark.parametrize("hand", ["left", "right"])
def test_wrist_language_pickers_and_swap_update_shared_settings(wrist, steamvr, backend, app, hand):
    from dataclasses import replace
    from ui.backend import AUTO, LANGS
    saved, applied = [], []
    window = MainWindow(backend, Settings(my_lang="en", translated_to=["zh", "vi"],
                                         chatbox_follow=False, chatbox_custom_languages=["yue", "ko"]),
                        save=lambda s: saved.append(replace(s)))
    backend.apply_settings = lambda s: applied.append(replace(s))
    bind_wrist_controls(window, wrist.panel)
    wrist._window_settings = lambda: window.settings
    wrist.settings.hand = hand
    panel = wrist.panel

    def click(button):
        app.processEvents()
        other = aim_at_button(wrist, steamvr, button)
        for _ in range(5):
            wrist.tick()
        steamvr.triggers[other] = True
        wrist.tick()
        steamvr.triggers[other] = False
        wrist.tick()
        app.processEvents()
        wrist.tick()

    try:
        click(panel.my_lang)
        assert panel.language_menu.isVisible()
        assert not panel.language_choices[AUTO].isVisible()
        assert set(panel.language_choices) == {*LANGS, AUTO}
        for code in LANGS:
            choice = panel.language_choices[code]
            assert panel.rect().contains(choice.mapTo(panel, choice.rect().bottomRight()))
        click(panel.language_choices["ja"])
        click(panel.language_choices["en"])
        assert panel.language_menu.isVisible()
        assert window.settings.my_languages == window.my_lang.selected_codes() == ["ja"]
        assert panel._languages == (["ja"], [AUTO]) and not panel.swap.isEnabled()
        assert len(saved) == len(applied) == 2
        click(panel.language_choices["ja"])
        assert panel.language_choices["ja"].isChecked() and len(saved) == 2
        click(panel.language_choices["vi"])
        click(panel.language_choices["zh"])
        assert window.my_lang.selected_codes() == ["ja", "vi", "zh"]
        assert not panel.language_choices["ko"].isEnabled()
        click(panel.language_choices["ko"])
        assert len(saved) == 4
        click(panel.language_choices["vi"])
        click(panel.language_choices["zh"])
        click(panel.language_done)
        assert not panel.language_menu.isVisible()
        click(panel.their_lang)
        assert panel.language_choices[AUTO].isVisible()
        click(panel.language_choices["ko"])
        assert panel._languages == (["ja"], ["ko"]) and panel.swap.isEnabled()
        click(panel.language_choices["en"])
        click(panel.language_choices["vi"])
        assert panel._languages == (["ja"], ["ko", "en", "vi"]) and panel.swap.isEnabled()
        assert window.settings.their_languages == window.their_lang.selected_codes() == ["ko", "en", "vi"]
        assert saved[-1].their_languages == applied[-1].their_languages == ["ko", "en", "vi"]
        assert not panel.language_choices["zh"].isEnabled()
        click(panel.language_choices["zh"])
        assert len(saved) == 9  # a fourth language cannot silently replace a selection
        click(panel.language_choices["ko"])
        click(panel.language_choices["vi"])
        assert panel._languages == (["ja"], ["en"])
        assert saved[-1].their_languages == ["en"] and not saved[-1].their_lang2
        click(panel.language_choices["en"])
        assert panel._languages == (["ja"], [AUTO])
        assert panel.language_choices[AUTO].isChecked()
        click(panel.language_choices["ko"])
        click(panel.language_done)
        assert not panel.language_menu.isVisible()
        click(panel.swap)
        assert panel._languages == (["ko"], ["ja"])
        assert window.settings.my_languages == window.my_lang.selected_codes() == ["ko"]
        assert window.settings.their_languages == window.their_lang.selected_codes() == ["ja"]
        assert len(saved) == len(applied) == 14
        assert all(s.translated_to == ["zh", "vi"] and s.chatbox_custom_languages == ["yue", "ko"]
                   and not s.chatbox_follow for s in saved)
        window.settings.their_languages = ["ja", "zh", "yue"]
        window.settings_changed()
        wrist.tick()
        assert panel.swap.isEnabled() == window.swap_button.isEnabled()
        assert panel._languages == (["ko"], ["ja", "zh", "yue"])
        window.settings.my_languages = ["vi", "en", "zh"]
        window.settings_changed()
        wrist.tick()
        assert panel._languages == (["vi", "en", "zh"], ["ja", "zh", "yue"])
        click(panel.swap)
        assert window.my_lang.selected_codes() == ["ja", "zh", "yue"]
        assert window.their_lang.selected_codes() == ["vi", "en", "zh"]
        click(panel.their_lang)
        steamvr.room.pop(0)
        wrist.tick()
        assert not panel.language_menu.isVisible()  # losing gaze closes the menu
    finally:
        window.close()


@pytest.mark.parametrize("hand", ["left", "right"])
def test_trigger_drags_thin_scrollbar_and_cancels_on_lost_input(wrist, steamvr, backend, app, hand):
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QStyle, QStyleOptionSlider
    wrist.settings.hand = hand
    for number in range(30):
        backend.utterance.emit(Utterance(number, "speaker", original="Conversation " * 10, final=True))
    app.processEvents()
    app.processEvents()
    bar = wrist.panel.log.verticalScrollBar()
    selected = []
    wrist.panel.toggle_requested.connect(selected.append)

    def handle():
        option = QStyleOptionSlider()
        bar.initStyleOption(option)
        return bar.style().subControlRect(QStyle.CC_ScrollBar, option, QStyle.SC_ScrollBarSlider, bar)

    def aim(point):
        return aim_at_button(wrist, steamvr, bar, point)

    other = aim(handle().center())
    for _ in range(5):
        wrist.tick()
    assert bar.width() == 8
    before = bar.value()
    steamvr.triggers[other] = True
    wrist.tick()
    assert abs(bar.value() - before) <= 1  # grabbing the handle does not jump
    initial_uploads = len(steamvr.images)
    aim(QPoint(-4, 2))  # a small sideways drift keeps the drag
    wrist.tick()
    assert bar.value() == bar.minimum() and not wrist.panel.log._stick
    assert len(steamvr.images) == initial_uploads + 1  # immediate feedback
    aim(QPoint(4, bar.height() - 2))
    wrist.tick()
    assert bar.value() == bar.maximum() and wrist.panel.log._stick
    steamvr.triggers[other] = False
    wrist.tick()
    aim(QPoint(4, 2))
    wrist.tick()
    assert bar.value() == bar.maximum()  # release stops dragging

    for loss in ("gaze", "tracking", "miss"):
        # Grab just beside the thin handle: the controller target is wider than its paint.
        aim(QPoint(-4, handle().center().y()))
        steamvr.triggers[other] = True
        wrist.tick()
        assert wrist.panel._scroll_drag_offset is not None
        if loss == "gaze":
            steamvr.room.pop(0)
        elif loss == "tracking":
            steamvr.aims.pop(other)
        else:
            steamvr.aims[other][:, 3] += (10, 0, 0)
        wrist.tick()
        assert wrist.panel._scroll_drag_offset is None
        before = bar.value()
        aim(QPoint(4, 2))
        for _ in range(5):
            wrist.tick()
        assert bar.value() == before  # held trigger cannot resume after re-entry
        steamvr.triggers[other] = False
        wrist.tick()
    assert not selected
    assert len(set(steamvr.texture_ids[77])) == 1 and not steamvr.destroyed


def test_thumbstick_scroll_requires_gaze_and_a_panel_hit(wrist, steamvr, backend, app):
    for number in range(30):
        backend.utterance.emit(Utterance(number, "speaker", original="Conversation " * 10, final=True))
    app.processEvents()
    app.processEvents()
    other = aim_at_button(wrist, steamvr, wrist.panel.mic)
    for _ in range(5):
        wrist.tick()
    bar = wrist.panel.log.verticalScrollBar()
    before = bar.value()
    steamvr.scrolls[other] = 0.1  # thumbstick drift
    wrist.tick()
    assert bar.value() == before
    steamvr.scrolls[other] = 0.8
    wrist.tick()
    assert bar.value() < before
    before = bar.value()
    steamvr.room.pop(0)
    wrist.tick()
    assert bar.value() == before
    aim_at_button(wrist, steamvr, wrist.panel.mic)
    steamvr.aims[other][:, 3] += (10, 0, 0)
    wrist.tick()
    assert bar.value() == before


def test_changing_interface_language_refreshes_open_vr_settings(wrist, backend, app):
    from ui import i18n
    window = MainWindow(backend, Settings(), save=lambda s: None)
    wrist._window_settings = lambda: window.settings
    button = add_vr_button(window, wrist)
    try:
        wrist.tick()
        button.click()
        app.processEvents()
        old = next(dialog for dialog in window.findChildren(VrDialog) if dialog.isVisible())
        window._ui_lang_picked("zh")
        wrist.tick()
        app.processEvents()
        current = next(dialog for dialog in window.findChildren(VrDialog) if dialog.isVisible())
        assert current is not old
        assert current.windowTitle() == i18n.tr("Wrist display (SteamVR)")
        assert current.windowTitle() != "Wrist display (SteamVR)"
        assert i18n.tr("Wrist display (SteamVR)") in button.toolTip()
    finally:
        i18n.set_lang("en")
        window.close()


def test_input_initialization_retries_without_restarting_subtitles(wrist, steamvr, monkeypatch):
    import time
    monkeypatch.setattr(time, "monotonic", wrist.clock)
    aim_at_button(wrist, steamvr, wrist.panel.mic)
    steamvr.fail = "getActionHandle"
    wrist.tick()
    assert wrist.overlay.connected and "getActionHandle" in wrist.problem
    steamvr.fail = ""
    wrist.clock.now += display.RETRY_S
    for _ in range(5):
        wrist.tick()
    assert wrist.panel._pointer is not None and wrist.problem == ""
    assert steamvr.inits == 1 and steamvr.shutdowns == 0
