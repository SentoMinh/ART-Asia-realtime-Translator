"""Orbitable wrist preview using omoideshabou's hand and SteamVR placement maths."""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import (QColor, QImage, QLinearGradient, QPainter, QPixmap, QPolygonF,
                           QTransform)
from PySide6.QtWidgets import QLabel

from . import pose
from .config import VrSettings
from .panel import SIZE

# The simple limb remains a fallback if the optional preview asset is missing.
SLEEVE = QColor("#2a2d36")
GLOVE = QColor("#3a3f4a")
CONTROLLER = QColor("#14161c")
BG_TOP = QColor("#1a1d26")
BG_BOTTOM = QColor("#0b0b0d")

DEFAULT_SIZE = (360, 340)
VIEW_ANGLE = 55
DEFAULT_YAW = 28.0
DEFAULT_PITCH = 18.0
DEFAULT_DISTANCE = 0.58
ZOOM_RANGE = (0.28, 1.2)  # metres from the preview camera to the wrist
PITCH_LIMIT = 75.0
MESH_PATH = Path(__file__).resolve().parent.parent / "assets/hand/omoideshabou.npz"


@lru_cache(maxsize=1)
def hand_mesh():
    try:
        with np.load(MESH_PATH, allow_pickle=False) as data:
            vertices, faces, normals = (data[key].copy() for key in ("vertices", "faces", "normals"))
        if (vertices.ndim != 2 or vertices.shape[1] != 3 or faces.ndim != 2
                or faces.shape[1] != 3 or normals.shape != faces.shape or not len(faces)
                or not np.issubdtype(faces.dtype, np.integer) or faces.min() < 0
                or faces.max() >= len(vertices) or not np.isfinite(vertices).all()
                or not np.isfinite(normals).all()):
            return None
        return vertices, faces, normals
    except (OSError, ValueError, KeyError):
        return None


def unit(vector) -> np.ndarray:
    vector = np.asarray(vector, dtype=float)
    length = float(np.linalg.norm(vector)) or 1.0
    return vector / length


def watch_pose(hand: str) -> np.ndarray:
    """Controller held like checking a watch: forearm across the chest."""
    side = -1 if hand == "left" else 1
    position = np.array([-0.10 * side, 1.27, -0.34])
    towards_eyes = unit(np.array([0.0, 1.60, 0.0]) - position)
    towards_eyes[0] = 0
    towards_eyes = unit(towards_eyes)
    back = np.array([float(side), 0.0, 0.0])
    right = side * towards_eyes
    return np.column_stack([right, np.cross(back, right), back, position])


def mesh_transform(hand: str) -> np.ndarray:
    """Map the left-hand asset to either controller: +Y elbow, +Z back, +X thumb."""
    side = -1 if hand == "left" else 1
    return np.array([[0, 0, side, 0], [-1, 0, 0, 0], [0, 1, 0, 0.08]], dtype=float)


class Camera:
    def __init__(self, eyes: np.ndarray, target: np.ndarray, width: int):
        self.eyes = np.asarray(eyes, dtype=float)
        self.forward = unit(np.asarray(target, dtype=float) - self.eyes)
        world_up = np.array([0.0, 1.0, 0.0])
        self.right = unit(np.cross(self.forward, world_up))
        if float(np.linalg.norm(self.right)) < 1e-6:
            self.right = unit(np.cross(self.forward, (0.0, 0.0, 1.0)))
        self.up = np.cross(self.right, self.forward)
        self.focal = width / 2 / math.tan(math.radians(VIEW_ANGLE) / 2)
        self._cx = self._cy = 0.0

    def spot(self, point) -> tuple[QPointF, float]:
        offset = np.asarray(point, dtype=float) - self.eyes
        depth = float(offset @ self.forward)
        if depth < 0.05:
            depth = 0.05
        scale = self.focal / depth
        return (QPointF(self._cx + scale * float(offset @ self.right),
                        self._cy - scale * float(offset @ self.up)), scale)

    def set_frame(self, width: int, height: int) -> None:
        self._cx = width / 2
        self._cy = height / 2


def orbit_eyes(target: np.ndarray, yaw_deg: float, pitch_deg: float,
               distance: float = DEFAULT_DISTANCE) -> np.ndarray:
    yaw = math.radians(yaw_deg)
    pitch = math.radians(max(min(pitch_deg, PITCH_LIMIT), -PITCH_LIMIT))
    offset = np.array([
        distance * math.cos(pitch) * math.sin(yaw),
        distance * math.sin(pitch),
        distance * math.cos(pitch) * math.cos(yaw),
    ])
    return np.asarray(target, dtype=float) + offset


def limb(painter: QPainter, camera: Camera, start, end, radius_start, radius_end,
         color: QColor) -> None:
    (a, scale_a), (b, scale_b) = camera.spot(start), camera.spot(end)
    ra, rb = radius_start * scale_a, radius_end * scale_b
    along = np.array([b.x() - a.x(), b.y() - a.y()])
    length = float(np.linalg.norm(along)) or 1.0
    across = QPointF(-along[1] / length, along[0] / length)
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    painter.drawPolygon(QPolygonF([a + across * ra, b + across * rb,
                                   b - across * rb, a - across * ra]))
    painter.drawEllipse(a, ra, ra)
    painter.drawEllipse(b, rb, rb)


def draw(settings: VrSettings, panel_picture: QImage, *,
         size: tuple[int, int] = DEFAULT_SIZE,
         yaw_deg: float = DEFAULT_YAW, pitch_deg: float = DEFAULT_PITCH,
         distance: float = DEFAULT_DISTANCE) -> QImage:
    """Arm, controller and overlay from `settings`, viewed from an orbiting camera."""
    width, height = size
    hand = watch_pose(settings.hand)
    side = -1 if settings.hand == "left" else 1
    place = pose.compose(hand, pose.wrist_transform(
        settings.hand, settings.along_cm, settings.out_cm, settings.up_cm,
        settings.tilt_deg, settings.yaw_deg, settings.roll_deg))
    target = hand[:, 3] + hand[:, 2] * 0.08
    eyes = orbit_eyes(target, yaw_deg, pitch_deg, distance)
    camera = Camera(eyes, target, width)
    camera.set_frame(width, height)

    def room(x, y, z):
        return hand[:, :3] @ np.array([x, y, z], dtype=float) + hand[:, 3]

    picture = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
    painter = QPainter(picture)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    sky = QLinearGradient(0, 0, 0, height)
    sky.setColorAt(0, BG_TOP)
    sky.setColorAt(1, BG_BOTTOM)
    painter.fillRect(picture.rect(), sky)

    mesh = hand_mesh()
    near_faces = []
    if mesh is None:
        limb(painter, camera, room(0, -0.06, 0.42), room(0, -0.05, 0.10), 0.048, 0.036, SLEEVE)
        limb(painter, camera, room(0, -0.11, 0.05), room(0, 0.02, -0.05), 0.020, 0.022, CONTROLLER)
        limb(painter, camera, room(0.015 * side, -0.07, 0.07), room(0.02 * side, -0.03, 0.01),
             0.040, 0.042, GLOVE)
    else:
        vertices, faces, normals = mesh
        transform = mesh_transform(settings.hand)
        rotation = transform[:, :3]
        local = vertices @ rotation.T + transform[:, 3]
        world = local @ hand[:, :3].T + hand[:, 3]
        normals = normals @ rotation.T @ hand[:, :3].T
        offsets = world - eyes
        depths = offsets @ camera.forward
        scale = camera.focal / np.maximum(depths, 0.05)
        xs = camera._cx + scale * (offsets @ camera.right)
        ys = camera._cy - scale * (offsets @ camera.up)
        centers = world[faces].mean(axis=1)
        order = np.argsort(-depths[faces].mean(axis=1))
        shades = 0.35 + 0.65 * np.maximum(0, normals @ unit(eyes - target + (0, 0.5, 0)))
        colors = [QColor(int(88 * shade), int(98 * shade), int(116 * shade)) for shade in shades]
        polygons = [QPolygonF([QPointF(xs[j], ys[j]) for j in face]) for face in faces]
        # shortcut: triangles crossing the panel use their centers; split them if close-up intersection accuracy is needed.
        near = ((centers - place[:, 3]) @ place[:, 2]) * float((eyes - place[:, 3]) @ place[:, 2]) > 0
        painter.setPen(Qt.NoPen)
        painter.setRenderHint(QPainter.Antialiasing, False)  # no pale seams between touching triangles
        for i in order:
            if near[i]:
                near_faces.append(i)
            else:
                painter.setBrush(colors[i])
                painter.drawPolygon(polygons[i])

    panel_w = settings.width_cm / 100
    panel_h = panel_w * SIZE[1] / SIZE[0]
    corners = [camera.spot(place[:, :3] @ np.array([x * panel_w / 2, y * panel_h / 2, 0.0])
                           + place[:, 3])[0]
               for x, y in ((-1, 1), (1, 1), (1, -1), (-1, -1))]
    flat = QPolygonF([QPointF(0, 0), QPointF(SIZE[0], 0),
                      QPointF(SIZE[0], SIZE[1]), QPointF(0, SIZE[1])])
    onto = QTransform()
    if float((eyes - place[:, 3]) @ place[:, 2]) > 0 and QTransform.quadToQuad(flat, QPolygonF(corners), onto):
        painter.save()
        painter.setOpacity(settings.opacity / 100)
        painter.setTransform(onto)
        painter.drawImage(0, 0, panel_picture)
        painter.restore()
    for i in near_faces:
        painter.setBrush(colors[i])
        painter.drawPolygon(polygons[i])
    painter.end()
    return picture


class ArmPreview(QLabel):
    """Drag to orbit the wrist; use the wheel to move the preview camera closer/further."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(*DEFAULT_SIZE)
        self.setCursor(Qt.OpenHandCursor)
        self.setAccessibleName("Arm preview")
        self._yaw = DEFAULT_YAW
        self._pitch = DEFAULT_PITCH
        self._distance = DEFAULT_DISTANCE
        self._drag: QPoint | None = None
        self._settings = VrSettings()
        self._panel = QImage(*SIZE, QImage.Format_ARGB32_Premultiplied)
        self._panel.fill(Qt.transparent)
        self.redraw()

    def set_scene(self, settings: VrSettings, panel_picture: QImage) -> None:
        self._settings = settings
        self._panel = panel_picture
        self.redraw()

    def redraw(self) -> None:
        width = max(self.width(), DEFAULT_SIZE[0])
        height = max(self.height(), DEFAULT_SIZE[1])
        picture = draw(self._settings, self._panel, size=(width, height),
                       yaw_deg=self._yaw, pitch_deg=self._pitch, distance=self._distance)
        self.setPixmap(QPixmap.fromImage(picture))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.redraw()

    def wheelEvent(self, event):
        steps = event.angleDelta().y() / 120 or event.pixelDelta().y() / 60
        if not steps:
            event.ignore()
            return
        self._distance = max(ZOOM_RANGE[0], min(ZOOM_RANGE[1],
            self._distance * 0.9 ** max(-10, min(10, steps))))
        self.redraw()
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag is not None and event.buttons() & Qt.LeftButton:
            now = event.position().toPoint()
            delta = now - self._drag
            self._drag = now
            self._yaw = (self._yaw - delta.x() * 0.4) % 360
            self._pitch = max(min(self._pitch + delta.y() * 0.3, PITCH_LIMIT), -PITCH_LIMIT)
            self.redraw()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = None
            self.setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(event)
