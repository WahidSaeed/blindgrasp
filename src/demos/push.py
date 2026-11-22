"""Demo 2: few-shot pushing.

Context rows: (sideways offset, push distance, push speed) -> puck displacement in
the push frame (along = forward along the push, left = sideways). The table is uniform, but the arm is not: the same
commanded push slides 2.9-3.6 cm depending on its direction, because the joints move differently and the paddle's
real speed at contact differs. DIR_FEATURE adds the direction as an input, but it is off: with only 3-10 pushes the
two extra inputs made predictions worse (GP, 4 seeds: median miss 0.36 cm with it, 0.14 cm without). One regressor
per target.

Planner: sample ~500 candidate pushes aimed roughly at the goal, predict where each leaves the puck,
pick the one landing closest + kappa * predicted spread (kappa > 0 cautious, < 0 exploring). The default
kappa = 1 prefers pushes the model is sure of: near pushes it has already made, not extrapolations. Without
it the planner, aiming at a goal out of reach, kept picking the push with the most optimistic predicted
slide, and the puck fell short or overshot by 1-2 cm. Pushes are planned with the paddle centred on the
puck (offset 0): the offset barely changes the slide (< 3 mm) and only added a dimension to learn.
Replan after every push until the puck is within GOAL_TOL of the goal.

Change handling (a push missing its prediction by > 2x the predicted spread = the physics changed):
  window : always keep only the last WINDOW pushes
  reset  : clear the context when a change is detected (keep the surprising push, it's from the new physics)
  none   : keep everything (shows the robot getting stuck when the world changes)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.learn.baselines import make_learner
from src.learn.tabpfn_service import LearnerService
from src.sim.env import PADDLE_HALF_T, PUCK_R, in_workspace
from src.sim.primitives import runup

GOAL_TOL = 0.03
N_SEED = 3
N_CANDIDATES = 500
WINDOW = 8
OFFSET_RANGE = (-0.015, 0.015)   # random strikes for eval/calibration.py; planned pushes use PLAN_OFFSET
PLAN_OFFSET = 0.0
KAPPA = 1.0
DIR_FEATURE = False


def features(offset, distance, speed, angle) -> np.ndarray:
    """Push -> model input row(s). Works on scalars or arrays."""
    cols = [offset, distance, speed] + ([np.cos(angle), np.sin(angle)] if DIR_FEATURE else [])
    return np.column_stack([np.broadcast_to(np.asarray(c, float), np.shape(speed)) for c in cols]) \
        if np.ndim(speed) else np.array(cols, float)
DIST_RANGE = (0.005, 0.04)    # paddle follow-through after contact (m); the puck may slide much further
SPEED_RANGE = (0.05, 0.45)    # paddle speed at contact (m/s): the puck's slide grows ~ speed^2 / friction.
                              # Capped so that on the icy setting a full-speed strike (~15 cm slide) stays on the table.
# Seed pushes: (follow-through, speed) spread over the action space - a slow carry, a medium and a fast strike - so the
# first model has anchors along the steep, nonlinear speed -> slide curve instead of three random points. None = random.
SEED_DESIGN = [(0.035, 0.12), (0.02, 0.25), (0.005, 0.35)]


@dataclass
class Plan:
    angle: float
    offset: float
    distance: float
    speed: float
    predicted_end: np.ndarray | None      # world xy
    spread: float | None                  # ~ half-width of the 10-90% band of the end point (m)
    random: bool                          # a seed/exploration push
    band: tuple | None = None             # (a10, a50, a90, l10, l50, l90): predicted displacement, push frame


@dataclass
class PushEvent:
    n: int
    miss: float | None       # |actual end - predicted end| (m)
    spread: float | None
    change: bool
    dropped: int
    goal_err: float


def push_geometry(puck_xy, angle: float, offset: float, distance: float, speed: float):
    u = np.array([np.cos(angle), np.sin(angle)])
    n = np.array([-u[1], u[0]])
    gap = runup(speed)
    back = PUCK_R + PADDLE_HALF_T + gap
    start = puck_xy - u * back + n * offset
    paddle_end = start + u * (gap + distance)
    return u, n, start, paddle_end


def feasible(puck_xy, angle, offset, distance, speed, along_guess) -> bool:
    _, _, start, paddle_end = push_geometry(np.asarray(puck_xy), angle, offset, distance, speed)
    u = np.array([np.cos(angle), np.sin(angle)])
    puck_end = np.asarray(puck_xy) + u * along_guess
    return in_workspace(*start, 0.01) and in_workspace(*paddle_end, 0.01) and in_workspace(*puck_end, 0.04)


class PushAgent:
    def __init__(self, learner: str = "gp", adapt: str = "reset", kappa: float = KAPPA, seed: int = 0,
                 window: int = WINDOW, learner_kwargs: dict | None = None, blocked=None):
        """blocked: optional f(points (k, 2)) -> bool array, True where a point is occupied (e.g. by a box
        on the touch map). Pushes whose paddle start or predicted puck path cross a blocked point are rejected."""
        self.learner_name, self.adapt, self.kappa, self.window = learner, adapt, kappa, window
        self.blocked = blocked
        self.rng = np.random.default_rng(seed)
        mk = lambda: make_learner(learner, **(learner_kwargs or {}))  # noqa: E731
        self.svc_along, self.svc_left = LearnerService(mk), LearnerService(mk)
        self.X: list[np.ndarray] = []
        self.Y: list[np.ndarray] = []
        self.n = 0
        self.version = 0
        self.events: list[PushEvent] = []
        self._cands = None

    # ---- context ------------------------------------------------------------------------------------
    def _trim(self, keep_last: int) -> int:
        d = max(0, len(self.X) - keep_last)
        if d:
            self.X, self.Y = self.X[d:], self.Y[d:]
            self.version += 1
        return d

    def clear(self) -> None:
        self.X, self.Y = [], []
        self.version += 1

    # ---- planning -------------------------------------------------------------------------------------
    def _sample(self, puck, goal, k: int, spread_angle: float, speed_max: float = SPEED_RANGE[1]):
        g = goal - puck
        base = np.arctan2(g[1], g[0])
        dist_needed = np.linalg.norm(g)
        a = base + self.rng.normal(0, spread_angle, k)
        if k > 1:  # 30% in any direction, so a sideways detour can beat pushes that are blocked or off the table
            wide = self.rng.random(k) < 0.3
            a[wide] = self.rng.uniform(-np.pi, np.pi, wide.sum())
        off = np.full(k, PLAN_OFFSET)
        dist = self.rng.uniform(DIST_RANGE[0], DIST_RANGE[1], k)
        spd = self.rng.uniform(SPEED_RANGE[0], speed_max, k)
        return a, off, dist, spd

    def plan_async(self, puck_xy, goal_xy):
        """Generator: yields while the learner predicts; returns a Plan, or None if no safe push exists."""
        puck, goal = np.asarray(puck_xy, float), np.asarray(goal_xy, float)
        if len(self.X) < N_SEED:
            # Seed pushes: aimed roughly at the goal, gentle (slow), so the puck stays on the table.
            # Aim roughly at the goal; if that's blocked (e.g. a box in the way), widen the aim step by step.
            for k_try in range(240):
                aim = (0.4, 1.0, 2.0, np.pi)[k_try // 60]
                a, off, dist, spd = (v[0] for v in self._sample(puck, goal, 1, aim, speed_max=0.35))
                if SEED_DESIGN is not None:
                    dist, spd = SEED_DESIGN[len(self.X) % len(SEED_DESIGN)]
                if not feasible(puck, a, off, dist, spd, dist):
                    continue
                if self.blocked is not None:
                    # No model yet: assume a gentle seed push slides the puck at most ~5 cm past the follow-through.
                    guess_end = puck + np.array([np.cos(a), np.sin(a)]) * (dist + 0.05)
                    if self._collides(puck, [a], [off], [spd], guess_end[None])[0]:
                        continue
                return Plan(a, off, dist, spd, None, None, True)
            return None

        a, off, dist, spd = self._sample(puck, goal, N_CANDIDATES, 0.25)
        ok = np.array([feasible(puck, a_, o_, d_, s_, d_) for a_, o_, d_, s_ in zip(a, off, dist, spd)])
        if ok.sum() < 20:
            ok[:] = True
        a, off, dist, spd = a[ok], off[ok], dist[ok], spd[ok]
        C = features(off, dist, spd, a)
        X, Y = np.stack(self.X), np.stack(self.Y)
        fa = self.svc_along.submit(self.version, X, Y[:, 0], C)
        fl = self.svc_left.submit(self.version, X, Y[:, 1], C)
        while not (fa.done() and fl.done()):
            yield
        if fa.exception() is not None or fl.exception() is not None:
            return None   # the fit failed (e.g. out of GPU memory); the caller sees the failed future and falls back
        (a10, a50, a90), (l10, l50, l90) = (fa.result().q10, fa.result().q50, fa.result().q90), \
                                            (fl.result().q10, fl.result().q50, fl.result().q90)
        u = np.column_stack([np.cos(a), np.sin(a)])
        nrm = np.column_stack([-u[:, 1], u[:, 0]])
        end = puck + a50[:, None] * u + l50[:, None] * nrm
        spread = 0.5 * np.hypot(a90 - a10, l90 - l10)
        score = np.linalg.norm(end - goal, axis=1) + self.kappa * spread
        # Don't plan pushes predicted (pessimistically, at the 90% quantile) to send the puck off the workspace.
        far = puck + a90[:, None] * u + l50[:, None] * nrm
        score[[not in_workspace(*e, 0.04) for e in far]] += 1.0
        if self.blocked is not None:
            score[self._collides(puck, a, off, spd, far)] += 1.0
        k = int(np.argmin(score))
        if score[k] >= 1.0:
            return None  # every candidate would leave the workspace or hit something on the map
        band = tuple(float(v[k]) for v in (a10, a50, a90, l10, l50, l90))
        return Plan(float(a[k]), float(off[k]), float(dist[k]), float(spd[k]), end[k], float(spread[k]), False, band)

    def _collides(self, puck, a, off, spd, far) -> np.ndarray:
        """True for candidates whose paddle start, or the puck's path to its (pessimistic) end, hits a blocked
        point. The puck path is checked along its centre line and both edges (+-PUCK_R)."""
        ts = np.linspace(0.0, 1.0, 12)
        all_pts = []
        for i in range(len(a)):
            u = np.array([np.cos(a[i]), np.sin(a[i])])
            n = np.array([-u[1], u[0]])
            _, _, start, _ = push_geometry(puck, a[i], off[i], 0.0, spd[i])
            # Skip the first 2 cm of travel: the puck may already sit inside a box's safety margin, and pushing it
            # away from the box must stay allowed. Pushing *into* the box still hits samples further along.
            length = max(float(np.linalg.norm(far[i] - puck)), 1e-6)
            line = puck[None] + ts[ts * length >= 0.02][:, None] * (far[i] - puck)[None]
            line = np.concatenate([line, np.repeat(line[-1:] if len(line) else far[i][None], 12 - len(line), 0)])
            # The paddle comes down at `start` and runs up to the puck: check that strip too (paddle half-width 2 cm).
            run = start[None] + np.linspace(0.0, 0.7, 4)[:, None] * (puck - start)[None]
            pts = np.concatenate([line, line + n * PUCK_R, line - n * PUCK_R, run, run + n * 0.02, run - n * 0.02])
            all_pts.append(pts)
        if not all_pts:
            return np.zeros(0, bool)
        # one call for all candidates (the map lookup is the slow part)
        return self.blocked(np.concatenate(all_pts)).reshape(len(a), -1).any(1)

    def plan(self, puck_xy, goal_xy) -> Plan:
        gen = self.plan_async(puck_xy, goal_xy)
        try:
            while True:
                next(gen)
        except StopIteration as s:
            return s.value

    # ---- learning from a push ------------------------------------------------------------------------
    def observe(self, plan: Plan, along: float, left: float, end_xy, goal_xy) -> PushEvent:
        miss = None if plan.predicted_end is None else float(np.linalg.norm(np.asarray(end_xy) - plan.predicted_end))
        change, dropped = False, 0
        if miss is not None and len(self.X) >= N_SEED + 2:
            change = miss > max(2 * plan.spread, 0.015)
        self.X.append(features(plan.offset, plan.distance, plan.speed, plan.angle))
        self.Y.append(np.array([along, left]))
        self.version += 1
        if self.adapt == "window":
            dropped = self._trim(self.window)
        elif self.adapt == "reset" and change:
            dropped = self._trim(1)
        ev = PushEvent(self.n, miss, plan.spread, change, dropped, float(np.linalg.norm(np.asarray(end_xy) - goal_xy)))
        self.events.append(ev)
        self.n += 1
        return ev

    def shutdown(self) -> None:
        self.svc_along.shutdown()
        self.svc_left.shutdown()


# ---- one push, then find the puck by touch ------------------------------------------------------------------
def search_prior(belief_xy, p: Plan, felt_puck: bool):
    from src.demos.puck_search import prior_predicted, prior_seed, prior_unmoved

    if not felt_puck:
        return prior_unmoved(belief_xy, p.angle)
    if p.band is None:
        return prior_seed(belief_xy, p.angle, p.distance)
    return prior_predicted(belief_xy, p.angle, p.band)


def execute_push(sim, agent: PushAgent, p: Plan, belief, goal, ui: dict, hover: float | None = None):
    """Generator: strike, feel for the puck where the push model says it should be, learn from where it was found.
    Returns (PushResult, PushEvent | None, SearchResult). The event is None when nothing was learned (the paddle
    missed the puck, or the puck could not be found)."""
    from src.demos.puck_search import locate_puck
    from src.sim.env import SAFE_Z
    from src.sim.primitives import push, push_frame

    start = belief.xy.copy()
    ui["status"] = "seed push (random)" if p.random else "pushing"
    r = yield from push(sim, p.angle, p.offset, p.distance, p.speed, start)
    ui["plan"] = None
    ui["status"] = "feeling for the puck" + ("" if r.felt_puck else ": the paddle didn't feel it")
    s = yield from locate_puck(sim, search_prior(start, p, r.felt_puck), hover=hover or SAFE_Z, ui=ui, seed=agent.n)
    true_err = None if s.xy is None else float(np.linalg.norm(s.xy - r.true_end_xy))   # simulator truth: shown, never used
    where = "" if s.xy is None else f" at ({s.xy[0]:.2f}, {s.xy[1]:.2f})"
    check = "" if true_err is None else f" [check vs simulator: {true_err * 100:.1f} cm off]"
    if s.xy is None:
        belief.known = False
        ui["log"].append(f"lost the puck after {s.n} touches - put it back on the table to tell the robot where it is")
        return r, None, s
    belief.tell(s.xy)
    if not r.felt_puck:
        ui["log"].append(f"the paddle didn't feel the puck; found it by touch after {s.n} touches{where}{check}")
        return r, None, s
    along, left = push_frame(s.xy - start, p.angle)
    ev = agent.observe(p, along, left, s.xy, goal)
    ui["pushes"].append({"n": ev.n + 1, "goal_cm": ev.goal_err * 100,
                         "miss_cm": None if ev.miss is None else ev.miss * 100,
                         "spread_cm": None if ev.spread is None else ev.spread * 100, "change": ev.change,
                         "search_touches": s.n, "true_err_cm": None if true_err is None else true_err * 100})
    ui["log"].append(f"push {ev.n + 1}: felt the puck after {s.n} touches{where}"
                     + (" (not where predicted: searched wider)" if s.widened else "") + check)
    if ev.change:
        ui["log"].append(f"push {ev.n + 1}: missed prediction by {ev.miss*100:.1f} cm (> 2x spread "
                         f"{ev.spread*100:.1f} cm): physics changed" + (f", dropped {ev.dropped} old pushes" if ev.dropped else ""))
    return r, ev, s


# ---- live demo -----------------------------------------------------------------------------------------
def pushing_task(sim, agent: PushAgent, ui: dict):
    """Push forever: when the puck is away from the goal, plan, push, feel for the puck, learn; otherwise wait.
    The puck's position comes from being told (ui['puck_told']: task start, or a person placing it) and from touch.
    ui gets: 'plan' (start, predicted end), 'pushes' list of dicts for the charts, 'log' list of strings."""
    from src.demos.puck_search import PuckBelief, take_told
    from src.sim.primitives import wait

    belief = ui.setdefault("belief", PuckBelief())
    ui.setdefault("search_pts", [])
    while True:
        take_told(ui, belief)
        if not belief.known:
            ui["plan"], ui["status"] = None, "lost the puck - click it, then the table, to tell the robot where it is"
            yield
            continue
        puck = belief.xy
        goal = sim.goal_xy()
        if np.linalg.norm(puck - goal) <= GOAL_TOL:
            ui["plan"] = None
            ui["status"] = "at goal - move the goal marker"
            yield
            continue
        if not in_workspace(*puck, 0.03):
            ui["status"] = "puck out of reach - drag it back onto the table"
            ui["plan"] = None
            yield
            continue
        ui["status"] = "planning"
        p = yield from agent.plan_async(puck, goal)
        if p is None:
            ui["plan"], ui["status"] = None, "no safe push found - move the goal or the puck"
            yield from wait(sim, 1.0)   # re-plan once a second, not every physics step
            continue
        ui["plan"] = (puck.copy(), None if p.predicted_end is None else p.predicted_end.copy(), p.random)
        yield from execute_push(sim, agent, p, belief, goal, ui)
