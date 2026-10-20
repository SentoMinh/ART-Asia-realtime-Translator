import ctypes
from ctypes import wintypes
from types import SimpleNamespace

from vrc import chatbox


class Call:
    def __init__(self, function):
        self.function = function

    def __call__(self, *args):
        return self.function(*args)


def fake_windows(monkeypatch, windows):
    def pid(hwnd, output):
        ctypes.cast(output, ctypes.POINTER(wintypes.DWORD)).contents.value = windows[hwnd][0]
        return 1

    def rect(hwnd, output):
        value = ctypes.cast(output, ctypes.POINTER(wintypes.RECT)).contents
        value.right, value.bottom = windows[hwnd][3:5]
        return windows[hwnd][7]

    def point(hwnd, output):
        value = ctypes.cast(output, ctypes.POINTER(wintypes.POINT)).contents
        value.x, value.y = windows[hwnd][5:7]
        return 1

    api = SimpleNamespace(
        EnumWindows=Call(lambda callback, arg: all(callback(hwnd, arg) for hwnd in windows)),
        GetWindowThreadProcessId=Call(pid),
        IsWindowVisible=Call(lambda hwnd: windows[hwnd][1]),
        IsIconic=Call(lambda hwnd: windows[hwnd][2]),
        GetClientRect=Call(rect), ClientToScreen=Call(point))
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(user32=api))
    monkeypatch.setattr(chatbox, "process_ids", lambda: [42])
    return api


def test_find_largest_visible_vrchat_client_preserves_negative_screen_coordinates(monkeypatch):
    fake_windows(monkeypatch, {
        # pid, visible, minimized, width, height, screen x/y, rect succeeds
        1: (99, True, False, 4000, 3000, 0, 0, True),
        2: (42, False, False, 4000, 3000, 0, 0, True),
        3: (42, True, True, 4000, 3000, 0, 0, True),
        4: (42, True, False, 0, 0, 0, 0, True),
        5: (42, True, False, 4000, 3000, 0, 0, False),
        6: (42, True, False, 320, 240, 100, 100, True),
        7: (42, True, False, 1920, 1080, -1920, -100, True),
    })
    assert chatbox.vrchat_window_origin() == (-1920, -100)


def test_no_window_or_no_vrchat_process_does_not_find_another_app(monkeypatch):
    api = fake_windows(monkeypatch, {1: (99, True, False, 640, 480, 0, 0, True)})
    assert chatbox.vrchat_window_origin() is None
    monkeypatch.setattr(chatbox, "process_ids", lambda: [])
    api.EnumWindows = Call(lambda *args: (_ for _ in ()).throw(AssertionError("unexpected scan")))
    assert chatbox.vrchat_window_origin() is None
