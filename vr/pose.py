"""Where the panel sits on the arm, and whether its wearer is looking at it.

Plain numbers only (no SteamVR here). A pose is a 3 × 4 array as SteamVR gives it: three
columns for the directions right / up / back, and a fourth for the position, in metres.
A controller points along its own "forward" (the opposite of its third column); its second
column is up when it is held like a pistol.
"""
from __future__ import annotations

import math

import numpy as np

# The panel's own directions (reading direction, up, towards the reader) in the controller's.
# Looking at a wristwatch, the forearm lies across the chest: the fingers of the left hand
# point to the reader's right, the back of the hand faces the eyes, the thumb is nearest the
# body. So on the left hand text runs towards the fingers and faces out of the back of the
# hand; the right hand is the mirror image.
AXES = {"left": ((0, 0, -1), (0, -1, 0), (-1, 0, 0)),
        "right": ((0, 0, 1), (0, -1, 0), (1, 0, 0))}
FACING = (0.35, 0.60)   # how squarely the panel must face the head: fades in between these
GAZE = (0.60, 0.80)     # how directly the head must point at the panel


def wrist_transform(hand: str, along_cm: float, out_cm: float, up_cm: float,
                    tilt_deg: float, yaw_deg: float = 0, roll_deg: float = 0) -> np.ndarray:
    """The panel's pose relative to the controller: `along_cm` from the controller towards
    the elbow, turned `tilt_deg` around the arm, then `out_cm` off the arm and `up_cm` up the
    panel's own height. Yaw and roll rotate about the panel's center without moving it."""
    right, up, out = (np.array(axis, dtype=float) for axis in AXES[hand])
    turn = math.radians(tilt_deg)
    up, out = (math.cos(turn) * up + math.sin(turn) * out,
               -math.sin(turn) * up + math.cos(turn) * out)
    position = np.array([0.0, 0.0, along_cm / 100]) + out_cm / 100 * out + up_cm / 100 * up
    yaw = math.radians(yaw_deg)
    right, out = (math.cos(yaw) * right - math.sin(yaw) * out,
                  math.sin(yaw) * right + math.cos(yaw) * out)
    roll = math.radians(roll_deg)
    right, up = (math.cos(roll) * right + math.sin(roll) * up,
                 -math.sin(roll) * right + math.cos(roll) * up)
    return np.column_stack([right, up, out, position])


def compose(outer: np.ndarray, inner: np.ndarray) -> np.ndarray:
    """`inner` is given relative to `outer`; the answer is where that is in the room."""
    turn = outer[:, :3]
    return np.column_stack([turn @ inner[:, :3], turn @ inner[:, 3] + outer[:, 3]])


def pointer_hit(aim: np.ndarray, panel: np.ndarray, width_m: float,
                aspect: float) -> tuple[float, float] | None:
    """Controller -Z ray to the front of the panel; returns top-left based 0–1 coordinates."""
    origin = panel[:, :3].T @ (aim[:, 3] - panel[:, 3])
    direction = panel[:, :3].T @ -aim[:, 2]
    if origin[2] <= 0 or direction[2] >= -1e-6 or width_m <= 0 or aspect <= 0:
        return None
    distance = -origin[2] / direction[2]
    if not 0 < distance <= 2.0:
        return None
    x, y = (origin + distance * direction)[:2]
    u, v = x / width_m + 0.5, 0.5 - y / (width_m * aspect)
    if 0 <= u < 1 and 0 <= v < 1:
        return float(u), float(v)
    return None


def _ramp(value: float, edges: tuple[float, float]) -> float:
    low, high = edges
    return min(max((value - low) / (high - low), 0.0), 1.0)


def looked_at(head: np.ndarray, panel: np.ndarray) -> float:
    """0.0 – 1.0: how much the wearer is looking at the panel (both poses in the room).
    It needs the panel turned towards the face AND the face turned towards the panel, so an
    arm swinging through the view does not flash it."""
    to_head = head[:, 3] - panel[:, 3]
    distance = float(np.linalg.norm(to_head))
    if distance < 1e-6:
        return 1.0
    to_head = to_head / distance
    facing = float(np.dot(panel[:, 2], to_head))
    gaze = float(np.dot(-head[:, 2], -to_head))
    return min(_ramp(facing, FACING), _ramp(gaze, GAZE))
