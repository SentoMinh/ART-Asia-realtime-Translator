"""Check real Windows OpenGL uploads/readback without starting SteamVR or touching settings.

    python tools/check_vr_texture.py
"""
from __future__ import annotations

import ctypes
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import openvr
from PySide6.QtWidgets import QApplication

from vr.texture import OverlayTextures


def main():
    app = QApplication([])
    gl = ctypes.WinDLL("opengl32.dll")
    gl.glBindTexture.argtypes = [ctypes.c_uint, ctypes.c_uint]
    gl.glGetTexImage.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p]
    sizes = {77: (720, 480), 79: (16, 16)}

    class Receiver:
        def setOverlayTexture(self, handle, texture):
            assert texture.eType == openvr.TextureType_OpenGL
            assert texture.eColorSpace == openvr.ColorSpace_Gamma
            if handle in ids:
                assert ids[handle] == texture.handle, "Texture was replaced during an update"
            ids[handle] = texture.handle
            gl.glBindTexture(0x0DE1, texture.handle)
            readback = (ctypes.c_ubyte * expected.size)()
            gl.glGetTexImage(0x0DE1, 0, 0x1908, 0x1401, readback)
            assert gl.glGetError() == 0
            assert bytes(readback) == expected[::-1].tobytes(), "Pixels, alpha or vertical orientation changed"

    for _ in range(3):
        textures = OverlayTextures()
        ids = {}
        try:
            for frame in range(100):
                for handle, (width, height) in sizes.items():
                    expected = np.empty((height, width, 4), dtype=np.uint8)
                    expected[:] = (frame, 22, 33, 200)
                    expected[0] = (255, 0, 0, 255)
                    expected[-1] = (0, 0, 255, 0)
                    textures.submit(openvr, Receiver(), handle, expected.tobytes(), width, height)
            assert len(set(ids.values())) == 2
        finally:
            textures.close()
    print("PASS: 600 native GPU uploads/readbacks; stable panel/cursor textures, RGBA, orientation and cleanup.")


if __name__ == "__main__":
    main()
