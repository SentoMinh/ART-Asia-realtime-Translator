"""Persistent OpenGL textures for SteamVR, updated without clearing the visible image."""
from __future__ import annotations

import numpy as np

from PySide6.QtGui import QOffscreenSurface, QOpenGLContext, QSurfaceFormat
from PySide6.QtOpenGL import QOpenGLTexture


class TextureError(RuntimeError):
    """The graphics context or texture could not be used."""


class OverlayTextures:
    def __init__(self):
        self._textures = {}
        self._context = QOpenGLContext()
        format = QSurfaceFormat()
        format.setRenderableType(QSurfaceFormat.OpenGL)
        self._context.setFormat(format)
        if not self._context.create() or self._context.isOpenGLES():
            raise TextureError("Could not create desktop OpenGL for the wrist display")
        self._surface = QOffscreenSurface()
        self._surface.setFormat(self._context.format())
        self._surface.create()
        if not self._surface.isValid():
            raise TextureError("Could not create the wrist display graphics surface")

    def submit(self, vr, overlay, handle: int, rgba: bytes, width: int, height: int) -> None:
        if width <= 0 or height <= 0 or len(rgba) != width * height * 4:
            raise TextureError("Invalid wrist display image dimensions")
        if not self._context.makeCurrent(self._surface):
            raise TextureError("The wrist display graphics context was lost")
        try:
            texture = self._textures.get(handle)
            if texture is not None and (texture.width(), texture.height()) != (width, height):
                raise TextureError("Wrist display texture size changed; reconnect to resize")
            if texture is None:
                texture = QOpenGLTexture(QOpenGLTexture.Target2D)
                self._textures[handle] = texture
                texture.setFormat(QOpenGLTexture.RGBA8_UNorm)
                texture.setSize(width, height)
                texture.setMipLevels(1)
                texture.setMinMagFilters(QOpenGLTexture.Linear, QOpenGLTexture.Linear)
                texture.setWrapMode(QOpenGLTexture.ClampToEdge)
                texture.allocateStorage(QOpenGLTexture.RGBA, QOpenGLTexture.UInt8)
                if not texture.isStorageAllocated():
                    raise TextureError("Could not allocate the wrist display texture")
            # Keep the texture/storage alive; only its pixels change during interaction.
            # Qt images start at the top; OpenGL textures start at the bottom.
            pixels = np.frombuffer(rgba, dtype=np.uint8).reshape(height, width, 4)[::-1].tobytes()
            texture.setData(QOpenGLTexture.RGBA, QOpenGLTexture.UInt8, pixels)
            functions = self._context.functions()
            functions.glFinish()
            if functions.glGetError():
                raise TextureError("Could not upload the wrist display texture")
            descriptor = vr.Texture_t(texture.textureId(), vr.TextureType_OpenGL, vr.ColorSpace_Gamma)
            overlay.setOverlayTexture(handle, descriptor)
            functions.glFlush()
        finally:
            self._context.doneCurrent()

    def close(self) -> None:
        if self._context.makeCurrent(self._surface):
            for texture in self._textures.values():
                texture.destroy()
            self._context.doneCurrent()
        self._textures.clear()
        self._surface.destroy()
