"""Map overlay drawn into viewer.user_scn: height tiles, probe dots, next-target ring, goal path.

Tiles: one thin box per grid cell, drawn at the predicted height; colour = height, alpha = confidence
(faded where the 10-90% band is wide). Call `draw(viewer.user_scn, ...)` once per frame inside
viewer.lock().
"""
from __future__ import annotations

import mujoco
import numpy as np

TILE_THICK = 0.002
MAX_H = 0.12  # colour scale top (tallest box)


def _height_rgb(h: float) -> np.ndarray:
    """Blue (table) -> yellow -> red (tall)."""
    t = float(np.clip(h / MAX_H, 0, 1))
    stops = np.array([[0.15, 0.35, 0.85], [0.95, 0.85, 0.2], [0.9, 0.2, 0.15]])
    if t < 0.5:
        return stops[0] + (stops[1] - stops[0]) * (t / 0.5)
    return stops[1] + (stops[2] - stops[1]) * ((t - 0.5) / 0.5)


def _add(scn: mujoco.MjvScene, gtype, size, pos, rgba, mat=None) -> bool:
    if scn.ngeom >= scn.maxgeom:
        return False
    g = scn.geoms[scn.ngeom]
    mujoco.mjv_initGeom(g, gtype, np.asarray(size, float), np.asarray(pos, float),
                        np.eye(3).ravel() if mat is None else mat, np.asarray(rgba, np.float32))
    g.category = mujoco.mjtCatBit.mjCAT_DECOR
    scn.ngeom += 1
    return True


class Overlay:
    def __init__(self, xs: np.ndarray, ys: np.ndarray, band_full: float = 0.002, band_empty: float = 0.06):
        """xs, ys: grid cell centres. Uncertainty band <= band_full is drawn opaque, >= band_empty faint."""
        self.xs, self.ys = np.asarray(xs), np.asarray(ys)
        self.half = (np.diff(self.xs[:2])[0] / 2 * 0.92, np.diff(self.ys[:2])[0] / 2 * 0.92)
        self.band_full, self.band_empty = band_full, band_empty

    def draw(
        self,
        scn: mujoco.MjvScene,
        height: np.ndarray | None = None,       # (len(ys), len(xs)) predicted median
        band: np.ndarray | None = None,         # (len(ys), len(xs)) q90 - q10
        probes: list[tuple[float, float, float, bool]] = (),  # (x, y, h, on_object)
        next_target: tuple[float, float] | None = None,
        truth: np.ndarray | None = None,        # ground-truth heights, drawn as wireframe-ish tiles
        path: list[tuple[float, float]] | None = None,
        path_ok: bool = True,
        mask: np.ndarray | None = None,         # (len(ys), len(xs)) cells to draw; default all
        clear: bool = True,                     # False to append to a scene that already holds the model
        puck: tuple[float, float] | None = None,  # where the robot believes the puck is (drawn as a cyan ring)
    ) -> None:
        if clear:
            scn.ngeom = 0
        if mask is None:
            mask = np.ones((len(self.ys), len(self.xs)), bool)
        if height is not None:
            band = np.zeros_like(height) if band is None else band
            conf = 1 - np.clip((band - self.band_full) / (self.band_empty - self.band_full), 0, 1)
            for j, y in enumerate(self.ys):
                for i, x in enumerate(self.xs):
                    if not mask[j, i]:
                        continue
                    h = float(height[j, i])
                    rgba = (*_height_rgb(h), 0.12 + 0.7 * conf[j, i])
                    _add(scn, mujoco.mjtGeom.mjGEOM_BOX, (self.half[0], self.half[1], TILE_THICK),
                         (x, y, max(h, 0) + TILE_THICK + 0.001), rgba)
        if truth is not None:
            for j, y in enumerate(self.ys):
                for i, x in enumerate(self.xs):
                    if not mask[j, i]:
                        continue
                    _add(scn, mujoco.mjtGeom.mjGEOM_BOX, (self.half[0] * 0.3, self.half[1] * 0.3, 0.001),
                         (x, y, float(truth[j, i]) + 0.004), (1, 1, 1, 0.8))
        for x, y, h, on_obj in probes:
            rgba = (1.0, 0.55, 0.1, 1) if on_obj else (0.55, 0.55, 0.55, 1)
            _add(scn, mujoco.mjtGeom.mjGEOM_SPHERE, (0.006, 0, 0), (x, y, h + 0.007), rgba)
        if puck is not None:
            for k in range(24):  # ring of small spheres around the believed puck rim, just above its top
                a = 2 * np.pi * k / 24
                _add(scn, mujoco.mjtGeom.mjGEOM_SPHERE, (0.0025, 0, 0),
                     (puck[0] + 0.035 * np.cos(a), puck[1] + 0.035 * np.sin(a), 0.046), (0.25, 0.75, 0.95, 1))
        if next_target is not None:
            x, y = next_target
            for k in range(16):  # ring of small spheres
                a = 2 * np.pi * k / 16
                _add(scn, mujoco.mjtGeom.mjGEOM_SPHERE, (0.003, 0, 0),
                     (x + 0.02 * np.cos(a), y + 0.02 * np.sin(a), 0.2), (0.1, 1, 0.3, 1))
        if path:
            rgba = (0.1, 0.9, 0.3, 0.9) if path_ok else (1, 0.1, 0.1, 0.9)
            for (x0, y0), (x1, y1) in zip(path[:-1], path[1:]):
                if scn.ngeom >= scn.maxgeom:
                    break
                # mjv_connector only sets type/size/pose; initialise the rest first (else the renderer
                # reads stale fields from a previous frame and can crash).
                mujoco.mjv_initGeom(scn.geoms[scn.ngeom], mujoco.mjtGeom.mjGEOM_CAPSULE, np.zeros(3), np.zeros(3),
                                    np.eye(3).ravel(), np.asarray(rgba, np.float32))
                mujoco.mjv_connector(scn.geoms[scn.ngeom], mujoco.mjtGeom.mjGEOM_CAPSULE, 0.003,
                                     np.array([x0, y0, 0.045]), np.array([x1, y1, 0.045]))
                scn.geoms[scn.ngeom].rgba[:] = rgba
                scn.geoms[scn.ngeom].category = mujoco.mjtCatBit.mjCAT_DECOR
                scn.ngeom += 1
