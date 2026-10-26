"""Reduce the supplied hand OBJ for the wrist preview, retaining its surface.

    python tools/prepare_hand.py path/to/hand2_1.obj

Only NumPy is needed; the source OBJ is not included in the app.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np


def reduce_mesh(vertices: np.ndarray, faces: np.ndarray, cells: int = 48):
    """Merge nearby vertices and retain connected triangles, rather than sampling faces."""
    if not np.isfinite(vertices).all():
        raise ValueError("The hand must have finite dimensions")
    # Straighten the diagonal source arm so +Y is the forearm axis.
    _, axes = np.linalg.eigh(np.cov(vertices.T))
    along = axes[:, -1]
    along *= 1 if along[1] >= 0 else -1
    across = np.array([1., 0., 0.]) - along[0] * along
    across /= np.linalg.norm(across)
    vertices = vertices @ np.column_stack([across, along, np.cross(across, along)])
    low, high = vertices.min(axis=0), vertices.max(axis=0)
    extent = float((high - low).max())
    if not np.isfinite(vertices).all() or extent <= 0:
        raise ValueError("The hand must have finite, nonzero dimensions")
    vertices = (vertices - (low + high) / 2) * (0.30 / extent)
    grid = np.floor((vertices - vertices.min(axis=0)) / (0.30 / cells)).astype(int)
    _, groups = np.unique(grid, axis=0, return_inverse=True)
    counts = np.bincount(groups)
    merged = np.column_stack([np.bincount(groups, weights=axis) / counts for axis in vertices.T])
    faces = groups[faces]
    faces = faces[(faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2])
                  & (faces[:, 2] != faces[:, 0])]
    _, unique = np.unique(np.sort(faces, axis=1), axis=0, return_index=True)
    faces = faces[unique]
    triangles = merged[faces]
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    valid = lengths > 1e-10
    return merged.astype(np.float32), faces[valid].astype(np.int32), (normals[valid] / lengths[valid, None]).astype(np.float32)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent.parent
                        / "assets/hand/omoideshabou.npz")
    args = parser.parse_args()
    vertices, faces = [], []
    for line in args.source.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "v":
            vertices.append([float(value) for value in parts[1:4]])
        elif parts[0] == "f":
            indices = [int(value.split("/")[0]) for value in parts[1:]]
            indices = [value - 1 if value > 0 else len(vertices) + value for value in indices]
            if any(value < 0 or value >= len(vertices) for value in indices):
                raise ValueError("OBJ face references a missing vertex")
            faces.extend((indices[0], indices[i], indices[i + 1]) for i in range(1, len(indices) - 1))
    if not vertices or not faces:
        raise ValueError("OBJ contains no triangle mesh")
    vertices, faces, normals = reduce_mesh(np.asarray(vertices), np.asarray(faces))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.output, vertices=vertices, faces=faces, normals=normals,
                        credit="Hand model by omoideshabou", source=args.source.name)
    print(f"Saved {args.output}: {len(vertices)} vertices, {len(faces)} triangles")


if __name__ == "__main__":
    main()
