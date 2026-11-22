"""Demo 1: map the table by touch.

Each probe adds a row (x, y -> height) to the context; the learner predicts the median height and the
10/90% quantiles on a grid. The next probe goes where the band (q90 - q10) is widest, minus a small
travel penalty, plus a bonus for areas whose nearest probe is old (so the arm revisits and can notice a
moved box). A probe that lands far outside the predicted band means the world changed: rows within
8 cm are dropped so that area is re-mapped.

Viewer (macOS needs mjpython):
    .venv/bin/mjpython -m src.demos.touch_map --learner gp
    .venv/bin/mjpython -m src.demos.touch_map --learner tabpfn
Keys: F6 auto on/off, F7 reset, F8 ground-truth overlay. Drag a box: Ctrl + right-drag.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass

import numpy as np

from src.learn.baselines import make_learner
from src.learn.tabpfn_service import ContextTable, LearnerService
from src.sim.env import TIP_R, WORKSPACE_X, WORKSPACE_Y, Sim, in_workspace

GRID_STEP = 0.02
OCCUPIED = 0.01               # predicted height above this = occupied
SEED_PROBES = [(0.46, 0.0), (0.34, -0.24), (0.34, 0.24), (0.64, -0.24), (0.64, 0.24)]
SURPRISE_ERR = 0.02           # |measured - predicted| above this ...
SURPRISE_MARGIN = 0.01        # ... and this far outside the 10-90% band = a surprise, which is verified:
VERIFY_R = 0.01               # a probe within this of an old row that reads > SURPRISE_ERR differently
DROP_RADIUS = 0.08            # confirms a change; rows within DROP_RADIUS of it are dropped
TRAVEL_PENALTY = 0.01         # metres of band per metre of travel
AGE_BONUS = 0.006             # band-equivalent bonus (m) for cells whose nearest probe is AGE_FULL probes old
AGE_FULL = 40
MIN_SPACING = 0.012           # never probe closer than this to an existing row
RECHECK_EVERY = 5             # every Nth probe re-checks an old probe location ...
RECHECK_ON_OBJECT = 0.7       # ... preferring (with this probability) one that touched an object: moving a box
                              #     changes exactly those spots, so this finds moves quickly
LSE_WEIGHT = 1.0              # "lse" strategy: weight of the occupancy-boundary term (level-set estimation)


def make_grid(step: float = GRID_STEP):
    xs = np.arange(WORKSPACE_X[0], WORKSPACE_X[1] + 1e-9, step)
    ys = np.arange(WORKSPACE_Y[0], WORKSPACE_Y[1] + 1e-9, step)
    gx, gy = np.meshgrid(xs, ys)
    Q = np.column_stack([gx.ravel(), gy.ravel()])
    mask = np.array([in_workspace(x, y) for x, y in Q]).reshape(len(ys), len(xs))
    return xs, ys, Q, mask


@dataclass
class ProbeEvent:
    n: int
    x: float
    y: float
    height: float
    predicted: float | None
    surprise: bool        # far outside the predicted band (could be an edge or a change)
    dropped: int
    confirmed: bool = False   # re-touching an old point read differently: the world changed
    verify: tuple | None = None  # old point scheduled for re-checking after a surprise


class TouchMap:
    def __init__(self, learner: str = "gp", strategy: str = "active", seed: int = 0, step: float = GRID_STEP,
                 learner_kwargs: dict | None = None, pred_step: float | None = None, max_rows: int | None = None):
        """pred_step: if coarser than `step`, the learner predicts on a grid with this spacing and the result is
        bilinearly upsampled to the display/probing grid (the plan's fallback for a slow learner: ~4x fewer
        query points at 4 cm). max_rows: cap the context, keeping the most recent rows (slow-learner fallback)."""
        self.learner_name, self.strategy = learner, strategy
        self.max_rows = max_rows
        self.xs, self.ys, self.Q, self.mask = make_grid(step)
        if pred_step and pred_step > step + 1e-9:
            self.pxs = np.linspace(self.xs[0], self.xs[-1], max(2, round((self.xs[-1] - self.xs[0]) / pred_step) + 1))
            self.pys = np.linspace(self.ys[0], self.ys[-1], max(2, round((self.ys[-1] - self.ys[0]) / pred_step) + 1))
            gx, gy = np.meshgrid(self.pxs, self.pys)
            self.Qpred = np.column_stack([gx.ravel(), gy.ravel()])
        else:
            self.pxs = self.pys = None
            self.Qpred = self.Q
        self._flat_cache = (None, None)
        self.shape = self.mask.shape
        self.targets = self.Q[self.mask.ravel()]          # probe-able cells
        self.table = ContextTable(2)
        self.probe_idx: list[int] = []                    # probe number for each row (for age)
        self.service = LearnerService(lambda: make_learner(learner, **(learner_kwargs or {})))
        self.rng = np.random.default_rng(seed)
        self.n = 0
        self.events: list[ProbeEvent] = []
        self.verify_queue: list[tuple[float, float]] = []
        self.avoid: list[tuple[float, float, float]] = []  # (x, y, radius) never probed, e.g. the puck
        self._raster = self._raster_order()

    # ---- prediction ------------------------------------------------------------------------------
    def update(self) -> bool:
        """Start a refit if new rows arrived and the worker is idle (never blocks)."""
        if self.max_rows and len(self.table) > self.max_rows:
            drop = len(self.table) - self.max_rows
            self.probe_idx = self.probe_idx[drop:]
            self.table.window(self.max_rows)
        return self.service.submit_if_idle(self.table, self.Qpred)

    def _flat(self):
        """Latest (q10, q50, q90) on the display grid, flattened; upsampled from the prediction grid if coarser.
        None before the first fit. Cached per prediction."""
        p = self.service.latest
        if p is None:
            return None
        key, val = self._flat_cache
        if key is p:
            return val
        if self.pxs is None:
            val = (p.q10, p.q50, p.q90)
        else:
            from scipy.interpolate import RegularGridInterpolator

            shape = (len(self.pys), len(self.pxs))
            pts = self.Q[:, ::-1]  # (y, x)
            val = tuple(RegularGridInterpolator((self.pys, self.pxs), a.reshape(shape))(pts) for a in (p.q10, p.q50, p.q90))
        self._flat_cache = (p, val)
        return val

    def wait(self) -> None:
        """Block until the current fit (if any) is done and reflects the latest rows (headless eval)."""
        while True:
            if self.service.pending is not None:
                self.service.pending.result()
            if not self.update():
                return

    def prediction(self):
        """(q10, q50, q90) as grids, or None before the first fit."""
        f = self._flat()
        if f is None:
            return None
        return tuple(a.reshape(self.shape) for a in f)

    def _predict_at(self, x: float, y: float):
        f = self._flat()
        if f is None:
            return None
        i = int(np.argmin(np.sum((self.Q - (x, y)) ** 2, axis=1)))
        return f[0][i], f[1][i], f[2][i]

    # ---- choosing the next probe -----------------------------------------------------------------
    def _raster_order(self):
        """Coarse-to-fine boustrophedon sweeps over the whole workspace: every 4th cell (8 cm), then every
        2nd, then all, each pass skipping cells already visited."""
        order, seen = [], set()
        for s in (4, 2, 1):
            for i in range(0, len(self.xs), s):
                js = range(0, len(self.ys), s)
                for j in (js if (i // s) % 2 == 0 else reversed(js)):
                    if self.mask[j, i] and (i, j) not in seen:
                        seen.add((i, j))
                        order.append((float(self.xs[i]), float(self.ys[j])))
        return order

    def _avoided(self, x: float, y: float) -> bool:
        return any(np.hypot(x - ax, y - ay) < r for ax, ay, r in self.avoid)

    def next_target(self, tip_xy=None) -> tuple[float, float]:
        t = self._next_target(tip_xy)
        if not self._avoided(*t):
            return t
        # Fall back to the best non-avoided cell by the active score.
        saved, self.strategy = self.strategy, "active"
        try:
            ok = np.array([not self._avoided(x, y) for x, y in self.targets])
            return self._next_target(tip_xy, allowed=ok)
        finally:
            self.strategy = saved

    def _next_target(self, tip_xy=None, allowed=None) -> tuple[float, float]:
        if allowed is None and self.n < len(SEED_PROBES):
            return SEED_PROBES[self.n]
        while self.verify_queue:
            v = self.verify_queue.pop(0)
            if not self._avoided(*v):
                return v
        if self.strategy == "random":
            return tuple(self.targets[self.rng.integers(len(self.targets))])
        if self.strategy == "raster":
            return self._raster[(self.n - len(SEED_PROBES)) % len(self._raster)]
        # active / lse
        X, Yh = self.table.arrays()
        if allowed is None and RECHECK_EVERY and self.n % RECHECK_EVERY == 0 and len(X):
            on_obj = np.where(Yh > OCCUPIED)[0]
            if len(on_obj) and self.rng.random() < RECHECK_ON_OBJECT:
                return tuple(X[self.rng.choice(on_obj)])
            return tuple(X[self.rng.integers(len(X))])
        p = self._flat()
        T = self.targets
        m = self.mask.ravel()
        band = (p[2] - p[0])[m] if p is not None else np.zeros(len(T))
        score = band.copy()
        if self.strategy == "lse" and p is not None:
            # Level-set estimation: favour cells whose 10-90% band straddles the occupancy threshold,
            # i.e. where we can't yet tell table from box. Probes then trace box outlines.
            straddle = np.minimum(p[2][m] - OCCUPIED, OCCUPIED - p[0][m])
            score = 0.25 * band + LSE_WEIGHT * np.clip(straddle, 0, None)
        if len(X):
            d = np.linalg.norm(T[:, None, :] - X[None, :, :], axis=2)
            nearest = d.argmin(1)
            age = self.n - np.array(self.probe_idx)[nearest]
            score += AGE_BONUS * np.clip(age / AGE_FULL, 0, 1)
            score[d.min(1) < MIN_SPACING] = -np.inf
        if tip_xy is not None:
            score -= TRAVEL_PENALTY * np.linalg.norm(T - np.asarray(tip_xy)[:2], axis=1)
        if allowed is not None:
            score[~allowed] = -np.inf
        return tuple(T[int(np.argmax(score))])

    # ---- adding a measurement --------------------------------------------------------------------
    def skip(self) -> None:
        """Count a probe slot that produced no row (e.g. it touched the puck)."""
        self.n += 1

    def add_probe(self, x: float, y: float, height: float, t: float = 0.0) -> ProbeEvent:
        pred = self._predict_at(x, y)
        surprise, dropped, confirmed, verify = False, 0, False, None
        X, Y = self.table.arrays()
        d = np.linalg.norm(X - (x, y), axis=1) if len(X) else np.zeros(0)
        # 1) Direct contradiction: we touched (almost) the same spot before and it reads differently now.
        close = np.where(d < VERIFY_R)[0]
        if len(close) and np.any(np.abs(Y[close] - height) > SURPRISE_ERR):
            confirmed = True
            stale = np.zeros(len(X), bool)
            for k in close[np.abs(Y[close] - height) > SURPRISE_ERR]:
                stale |= np.linalg.norm(X - X[k], axis=1) <= DROP_RADIUS
            stale |= d <= DROP_RADIUS
            keep = ~stale
            self.probe_idx = [k for k, m in zip(self.probe_idx, keep) if m]
            dropped = self.table.keep(keep)
        # 2) Surprise vs the map: could be a box edge or a change. Don't drop anything yet; re-touch the
        #    nearest old point next. If that one changed too, (1) fires on the verification probe.
        elif pred is not None:
            lo, mid, hi = pred
            surprise = bool(abs(height - mid) > SURPRISE_ERR and (height > hi + SURPRISE_MARGIN or height < lo - SURPRISE_MARGIN))
            if surprise and len(X):
                far = d >= VERIFY_R
                if far.any():
                    k = int(np.where(far)[0][np.argmin(d[far])])
                    if d[k] <= DROP_RADIUS:
                        verify = (float(X[k, 0]), float(X[k, 1]))
                        self.verify_queue.append(verify)
        self.table.add((x, y), height, t)
        self.probe_idx.append(self.n)
        ev = ProbeEvent(self.n, x, y, height, None if pred is None else float(pred[1]), surprise, dropped,
                        confirmed, verify)
        self.events.append(ev)
        self.n += 1
        return ev

    # ---- scoring ----------------------------------------------------------------------------------
    def metrics(self, truth: np.ndarray, truth_geom: np.ndarray | None = None) -> dict:
        """Height MAE (m) and occupancy IoU over reachable cells.
        truth: what a probe would read at each cell (touch truth, see truth_grid); truth_geom: optional
        geometric heights (ray at the cell centre) for a secondary IoU."""
        pr = self.prediction()
        m = self.mask
        if pr is None:
            return {"mae": float("nan"), "iou": float("nan"), "band": float("nan")}
        q10, q50, q90 = pr
        occ_p, occ_t = q50[m] > OCCUPIED, truth[m] > OCCUPIED
        union = np.sum(occ_p | occ_t)
        out_geom = {}
        if truth_geom is not None:
            og = truth_geom[m] > OCCUPIED
            ug = np.sum(occ_p | og)
            out_geom = {"iou_geom": float(np.sum(occ_p & og) / ug) if ug else 1.0}
        return {
            **out_geom,
            "mae": float(np.mean(np.abs(q50[m] - truth[m]))),
            "iou": float(np.sum(occ_p & occ_t) / union) if union else 1.0,
            "band": float(np.mean((q90 - q10)[m])),
            "coverage": float(np.mean((truth[m] >= q10[m]) & (truth[m] <= q90[m]))),
        }

    def truth_grid(self, sim: Sim, footprint: bool = True) -> np.ndarray:
        """Ground truth per cell. footprint=True: the height a probe would feel there (highest surface under
        the 6 mm tip disc), which is what the map can learn; False: geometric height at the cell centre.
        The difference is a ~6 mm dilation of every box, which alone caps geometric IoU near 0.78."""
        if not footprint:
            return sim.true_height_grid(self.xs, self.ys)
        offs = [(0.0, 0.0)] + [(TIP_R * np.cos(a), TIP_R * np.sin(a)) for a in np.linspace(0, 2 * np.pi, 8, endpoint=False)]
        return np.array([[max(sim.true_height(x + dx, y + dy) for dx, dy in offs) for x in self.xs] for y in self.ys])

    def reset(self) -> None:
        self.table.clear()
        self.probe_idx.clear()
        self.events.clear()
        self.verify_queue.clear()
        self.n = 0
        self.service.latest = None


# ---- live demo ---------------------------------------------------------------------------------------
def mapping_task(sim: Sim, tm: TouchMap, ui: dict):
    """Probe forever: pick a target, probe, add the row, refit in the background."""
    from src.sim.primitives import probe_down

    while True:
        tip = sim.ctl.tip_pos()
        target = tm.next_target(tip)
        ui["next"] = target
        r = yield from probe_down(sim, *target)
        if r.contact:
            ev = tm.add_probe(r.x, r.y, r.height, sim.t)
            ui["probes"].append((r.x, r.y, r.height, r.height > 0.01))
            if ev.confirmed:
                kept = {tuple(np.round(x, 6)) for x in tm.table.arrays()[0]}
                ui["probes"] = [p for p in ui["probes"] if (round(p[0], 6), round(p[1], 6)) in kept]
        tm.update()


def main() -> None:
    import mujoco  # noqa: F401

    from src.sim.env import run_viewer
    from src.viz.overlay import Overlay

    ap = argparse.ArgumentParser()
    ap.add_argument("--learner", default="gp", choices=["tabpfn", "tabpfn_nn", "gp", "knn", "mlp"])
    ap.add_argument("--strategy", default="active", choices=["active", "lse", "random", "raster"])
    args = ap.parse_args()

    sim = Sim()
    tm = TouchMap(args.learner, args.strategy)
    ov = Overlay(tm.xs, tm.ys)
    ui = {"probes": [], "next": None, "truth": False, "truth_grid": None, "started": False}

    def next_task(s):
        if ui["started"]:
            return None
        ui["started"] = True
        return mapping_task(s, tm, ui)

    def on_key(action, s):
        if action == "reset":
            tm.reset()
            ui.update(probes=[], next=None, started=False)
        elif action == "truth":
            ui["truth"] = not ui["truth"]

    frame = {"k": 0}

    def on_frame(s, viewer):
        frame["k"] += 1
        tm.update()
        pr = tm.prediction()
        if ui["truth"] and frame["k"] % 30 == 1:
            ui["truth_grid"] = tm.truth_grid(s)
        ov.draw(viewer.user_scn,
                height=None if pr is None else pr[1], band=None if pr is None else pr[2] - pr[0],
                probes=ui["probes"], next_target=ui["next"],
                truth=ui["truth_grid"] if ui["truth"] else None, mask=tm.mask)

    run_viewer(sim, next_task, on_frame=on_frame, on_key=on_key)


if __name__ == "__main__":
    main()
