"""Find the puck by touch. The robot has no camera and never reads the puck's position from the simulator: it
knows where the puck was put at the start (the task says so, like the goal), and after every push it feels for it.

How the search works:
  - Candidate centres: a grid of possible puck centres, weighted by a prior. After a planned push the prior is the
    push model's prediction (median and 10-90% band, in the push frame). For a seed push there is no model yet, so
    the prior is a wide strip ahead of the puck. As TabPFN learns, the band narrows and the search needs fewer touches.
  - Each touch rules candidates out. The puck is a 4 cm tall disc of radius 3.5 cm and the boxes are 6-12 cm tall, so
    the height felt says what was touched: ~4 cm = the puck, taller = a box, ~0 = bare table. What presses down is not
    just the 6 mm tip: the 4 cm push paddle sits level with the tip centre, so near the puck the paddle lands on its rim
    first. Each touch is therefore modelled with its full footprint (tip + paddle bar, at the tool's current yaw, which
    the robot knows from its own joints): "puck" = the puck overlaps the footprint and the contact point is on it;
    "table" = the puck is clear of the whole footprint.
  - A strike moves the puck almost straight along the push line (sideways < 1 cm, forward 1-15 cm), and after the
    push the paddle lies across that line. So the search is mostly 1-D: how far along the line did it go? Priors are
    long and thin along the line; sideways the push model's own (narrow) band is trusted.
  - The next touch is where the remaining candidates split closest to 50/50 (puck there or not), so each touch
    roughly halves what is left. It stops once 90% of the remaining weight is within DONE_R of the estimate, along the
    line and across it separately.
  - If every candidate is ruled out, the puck is not where the model said (e.g. the table turned icy and it slid
    further): the search steps further along the push line; then, if that fails, over a wide area. If that fails too,
    the puck is lost.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from src.sim.env import PADDLE_HALF_T, PUCK_HALF_H, PUCK_R, SAFE_Z, TABLE_X, TABLE_Y, TIP_R, in_workspace

PUCK_TOP = 2 * PUCK_HALF_H        # 4 cm
PUCK_H = (0.025, 0.055)           # a touch in this height range felt the puck (boxes are >= 6 cm tall)
TABLE_H = 0.01                    # below this: bare table
TOL = 0.004                       # slack on the geometric tests (tip lag, edge contacts)
DONE_R = 0.006                    # stop when 90% of the remaining weight is within 6 mm of the estimate
MAX_TOUCHES = 18
LOW_HOVER = 0.08                  # tip-centre height for hops between search touches when nothing tall is near
MIN_SIGMA_A = 0.008               # floor on the prior's spread along the push (m)
MIN_SIGMA_L = 0.005               # ... and across it (sideways drift is small, < 1.5 cm, but not well predicted)
TRAVEL_PEN = 0.05                 # split-score penalty per metre of travel (prefers nearby touches on ties)
PADDLE_HALF_L = 0.02              # paddle half-length along the tool's x axis (assets/build_panda_probe.py)


@dataclass
class PuckBelief:
    """Where the robot thinks the puck is. Set by being told (start of the task, or a person placing it) or by
    finding it by touch. known=False after a failed search: the robot needs to be told again."""
    xy: np.ndarray | None = None
    known: bool = False

    def tell(self, xy) -> None:
        self.xy, self.known = np.asarray(xy, float).copy(), True


def take_told(ui: dict, belief: PuckBelief) -> bool:
    """Apply a 'the puck is here' message from the presenter / UI (ui['puck_told']). Returns True if one arrived."""
    told = ui.get("puck_told")
    if told is None:
        return False
    belief.tell(told)
    ui["puck_told"] = None
    return True


@dataclass
class Touch:
    x: float      # contact point (where something was felt; for "table" the tip position)
    y: float
    h: float
    kind: str     # puck | table | tall | edge
    qx: float = 0.0   # where the tip came down
    qy: float = 0.0
    yaw: float = 0.0  # tool yaw at the touch: sets the paddle's direction


def footprint_dist(C: np.ndarray, q, yaw: float) -> np.ndarray:
    """Distance from each candidate centre to the touch footprint's centre line: the paddle bar through q along the
    tool x axis (cos yaw, sin yaw), half-length PADDLE_HALF_L. The tip at q is on that line."""
    e = np.array([np.cos(yaw), np.sin(yaw)])
    diff = C - np.asarray(q)[None]
    t = np.clip(diff @ e, -PADDLE_HALF_L, PADDLE_HALF_L)
    return np.linalg.norm(diff - t[:, None] * e[None], axis=1)


def classify(h: float) -> str:
    if PUCK_H[0] <= h <= PUCK_H[1]:
        return "puck"
    if h < TABLE_H:
        return "table"
    if h > PUCK_H[1]:
        return "tall"
    return "edge"


@dataclass
class Prior:
    """Candidate region in a push frame: origin + along/left ranges, optional Gaussian weighting."""
    origin: np.ndarray
    angle: float
    along: tuple[float, float]
    left: tuple[float, float]
    mean: tuple[float, float] | None = None    # (along, left) of the most likely centre
    sigma: tuple[float, float] | None = None
    step: float = 0.0025
    label: str = ""

    def candidates(self) -> tuple[np.ndarray, np.ndarray]:
        u = np.array([np.cos(self.angle), np.sin(self.angle)])
        n = np.array([-u[1], u[0]])
        a = np.arange(self.along[0], self.along[1] + 1e-9, self.step)
        l = np.arange(self.left[0], self.left[1] + 1e-9, self.step)
        A, L = np.meshgrid(a, l)
        A, L = A.ravel(), L.ravel()
        C = self.origin[None] + A[:, None] * u[None] + L[:, None] * n[None]
        if self.mean is None:
            w = np.ones(len(C))
        else:
            w = np.exp(-0.5 * (((A - self.mean[0]) / self.sigma[0]) ** 2 + ((L - self.mean[1]) / self.sigma[1]) ** 2))
        # The puck is on the table (if it fell off, it can't be found by touching the table).
        on = ((C[:, 0] >= TABLE_X[0]) & (C[:, 0] <= TABLE_X[1]) & (C[:, 1] >= TABLE_Y[0]) & (C[:, 1] <= TABLE_Y[1]))
        return C[on], w[on]


def prior_predicted(start, angle: float, band) -> Prior:
    """From the push model: band = (a10, a50, a90, l10, l50, l90) of the puck's displacement in the push frame."""
    a10, a50, a90, l10, l50, l90 = band
    sa = max((a90 - a10) / 2 / 1.2816, MIN_SIGMA_A)
    sl = max((l90 - l10) / 2 / 1.2816, MIN_SIGMA_L)
    return Prior(np.asarray(start, float), angle, (a50 - 3 * sa - 0.01, a50 + 3 * sa + 0.01),
                 (l50 - 3 * sl - 0.004, l50 + 3 * sl + 0.004), (a50, l50), (sa, sl), step=0.002, label="predicted")


def prior_seed(start, angle: float, distance: float) -> Prior:
    """No push model yet: somewhere on a thin strip ahead of the puck along the push line."""
    return Prior(np.asarray(start, float), angle, (-0.01, distance + 0.20), (-0.012, 0.012), step=0.002, label="seed")


def prior_unmoved(start, angle: float) -> Prior:
    """The paddle felt nothing: the puck wasn't where the robot thought, and the push didn't move it."""
    return Prior(np.asarray(start, float), angle, (-0.07, 0.07), (-0.07, 0.07), step=0.003, label="not felt")


def prior_further(start, angle: float) -> Prior:
    """Not where predicted: most likely it slid further (or less) along the same line, e.g. on ice."""
    return Prior(np.asarray(start, float), angle, (-0.04, 0.40), (-0.025, 0.025), step=0.0025, label="along the line")


def prior_wide(start, angle: float) -> Prior:
    return Prior(np.asarray(start, float), angle, (-0.08, 0.35), (-0.15, 0.15), step=0.004, label="wide")


def consistent(C: np.ndarray, touches: list[Touch]) -> np.ndarray:
    ok = np.ones(len(C), bool)
    for t in touches:
        d = np.hypot(C[:, 0] - t.x, C[:, 1] - t.y)          # to the contact point
        f = footprint_dist(C, (t.qx, t.qy), t.yaw)           # to the whole footprint
        if t.kind == "puck":
            ok &= (d <= PUCK_R + TOL) & (f <= PUCK_R + max(TIP_R, PADDLE_HALF_T) + TOL)
        elif t.kind == "table":
            ok &= (f >= PUCK_R + PADDLE_HALF_T - TOL) & (np.hypot(C[:, 0] - t.qx, C[:, 1] - t.qy) >= PUCK_R + TIP_R - TOL)
        elif t.kind == "tall":
            ok &= d >= PUCK_R - TOL
        else:  # glancing contact on the rim
            ok &= (d >= PUCK_R - 0.012) & (d <= PUCK_R + TIP_R + TOL)
    return ok


def _r90(x, w) -> float:
    """Half-width around the weighted mean holding 90% of the weight (1-D)."""
    d = np.abs(x - (x * w).sum() / w.sum())
    o = np.argsort(d)
    cw = np.cumsum(w[o]) / w.sum()
    return float(d[o][min(np.searchsorted(cw, 0.9), len(d) - 1)])


def _spread(C, w, angle: float) -> tuple[float, float]:
    """90% half-widths of the remaining candidates along and across the push line."""
    u = np.array([np.cos(angle), np.sin(angle)])
    return _r90(C @ u, w), _r90(C @ np.array([-u[1], u[0]]), w)


def choose_touch(C, w, touches: list[Touch], tip_xy, yaw: float, rng) -> tuple[np.ndarray, float] | None:
    """Touch point whose outcome (puck / not puck, for the full tip + paddle footprint at this yaw) splits the
    remaining candidate weight closest to 50/50."""
    if len(C) > 2500:  # score on a weighted subsample; the split estimate doesn't need every candidate
        idx = rng.choice(len(C), 2500, replace=False, p=w / w.sum())
        Cs, ws = C[idx], np.ones(2500)
    else:
        Cs, ws = C, w
    lo, hi = Cs.min(0) - PUCK_R, Cs.max(0) + PUCK_R
    step = max(0.004, float(np.sqrt(np.prod(hi - lo) / 1500)))
    gx, gy = np.meshgrid(np.arange(lo[0], hi[0] + 1e-9, step), np.arange(lo[1], hi[1] + 1e-9, step))
    P = np.column_stack([gx.ravel(), gy.ravel()])
    P = P[[in_workspace(x, y) for x, y in P]]
    if touches:
        T = np.array([(t.qx, t.qy) for t in touches])
        P = P[np.min(np.linalg.norm(P[:, None] - T[None], axis=2), axis=1) > 0.004]
    if not len(P):
        return None
    e = np.array([np.cos(yaw), np.sin(yaw)])
    diff = Cs[None, :, :] - P[:, None, :]
    tt = np.clip(diff @ e, -PADDLE_HALF_L, PADDLE_HALF_L)
    f = np.linalg.norm(diff - tt[..., None] * e, axis=2)
    on = (ws[None] * (f <= PUCK_R + PADDLE_HALF_T)).sum(1) / ws.sum()
    split = np.minimum(on, 1 - on)
    score = split - TRAVEL_PEN * np.linalg.norm(P - np.asarray(tip_xy)[None], axis=1)
    k = int(np.argmax(score))
    return P[k], float(split[k])


@dataclass
class SearchResult:
    xy: np.ndarray | None
    touches: list[Touch] = field(default_factory=list)
    widened: bool = False
    prior: str = ""

    @property
    def n(self) -> int:
        return len(self.touches)


def locate_puck(sim, prior: Prior, hover: float = SAFE_Z, ui: dict | None = None, max_touches: int = MAX_TOUCHES,
                seed: int = 0):
    """Generator: touch until the puck's centre is pinned down. Returns a SearchResult (xy None = not found)."""
    from src.sim.primitives import probe_down

    rng = np.random.default_rng(seed)
    C, w = prior.candidates()
    res = SearchResult(None, prior=prior.label)
    # If the puck isn't in this prior, step further along the push line, then search wide.
    fallbacks = [prior_further(prior.origin, prior.angle), prior_wide(prior.origin, prior.angle)]
    if prior.label == "not felt":
        fallbacks = fallbacks[1:]
    if ui is not None:
        ui["search_pts"] = []
    while True:
        m = consistent(C, res.touches)
        if not m.any():
            if not fallbacks:
                return res                      # lost
            nxt = fallbacks.pop(0)
            C, w = nxt.candidates()
            res.widened = True
            if ui is not None:
                ui["status"] = f"feeling for the puck: not where predicted, searching {nxt.label}"
            continue
        Cm, wm = C[m], w[m]
        if wm.sum() <= 0:
            wm = np.ones(len(Cm))
        est = (Cm * wm[:, None]).sum(0) / wm.sum()
        felt = any(t.kind == "puck" for t in res.touches)
        if felt and max(_spread(Cm, wm, prior.angle)) <= DONE_R:
            res.xy = est
            return res
        if res.n >= max_touches:
            res.xy = est if felt else None
            return res
        yaw = sim.ctl.set_yaw           # probe_down keeps the tool yaw, so this is the yaw the touch will have
        pick = choose_touch(Cm, wm, res.touches, sim.ctl.tip_pos()[:2], yaw, rng)
        if pick is None or pick[1] < 0.03:
            if felt:
                res.xy = est             # no touch would split what is left: done
                return res
            q = est                      # narrowed down but not felt yet: touch the most likely centre
        else:
            q = pick[0]
        if ui is not None:
            ui["next"] = (float(q[0]), float(q[1]))
        r = yield from probe_down(sim, float(q[0]), float(q[1]), hover=hover)
        h = r.height if r.contact else 0.0
        t = Touch(r.x, r.y, h, classify(h), float(q[0]), float(q[1]), yaw)
        res.touches.append(t)
        if ui is not None:
            ui["search_pts"].append((t.x, t.y, t.h, t.kind != "table"))
            ui["next"] = None
