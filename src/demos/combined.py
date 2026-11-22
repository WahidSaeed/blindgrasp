"""Acts 1 + 2 in one run: map by touch, then push the puck to the goal around the boxes the map found.

State machine:
  MAP   until MAP_PROBES probes, or the map's mean 10-90% band over reachable cells drops below BAND_DONE
  PUSH  plan pushes; candidates whose predicted puck path crosses an occupied map cell are rejected
  back to MAP for REMAP_PROBES probes along the puck's path when a push surprises us (it may have hit
  something the map doesn't know about), then PUSH again

Live: `python -m src.web.server --mode combined`.
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import maximum_filter

from src.demos.push import GOAL_TOL, PushAgent
from src.demos.touch_map import OCCUPIED, TouchMap
from src.sim.env import PUCK_R, in_workspace

MAP_PROBES = 45
BAND_DONE = 0.012
REMAP_PROBES = 4
CLEARANCE = 0.015   # keep the puck this far from occupied cells (on top of its radius, checked at its edges)
PROBE_CLEAR = PUCK_R + 0.035  # never probe closer than this to the puck centre: the paddle on the probe rod sits
                             # level with the tip and reaches 2 cm sideways, so a closer probe can shove the puck
TOUCH_BLOCK = 0.035  # path points this close to a touched-tall spot are blocked (box half-width ~ 3.5 cm)
ROUTE_STEP = 0.03   # route check: sample the puck's path (centre and both edges) every 3 cm ...
ROUTE_FRESH = 0.025 # ... and touch any sample with no push-phase probe within 2.5 cm ...
ROUTE_MAX = 3       # ... at most this many (the nearest) per push, then push if they were clear
SEED_REACH = 0.08   # assumed path length for a seed push (no prediction yet)


def make_blocked(tm: TouchMap, puck_xy_fn):
    """f(points) -> True where the current touch map says 'occupied' (median height > OCCUPIED), ignoring
    the puck's own footprint (the probe may have touched the puck)."""
    def blocked(pts: np.ndarray) -> np.ndarray:
        # Hard evidence first: anywhere we have *touched* something tall (rows still in the context, so
        # stale touches dropped after a box move don't count) is blocked whatever the learned map says.
        X, y = tm.table.arrays()
        tall = X[y > OCCUPIED] if len(X) else np.zeros((0, 2))
        hard = np.zeros(len(pts), bool)
        if len(tall):
            hard = (np.linalg.norm(pts[:, None, :] - tall[None], axis=2) < TOUCH_BLOCK).any(1)
        # Touches on the puck are never stored, so hard evidence needs no puck exclusion. The learned map can
        # still smear a bump near the puck, so ignore it right next to the puck.
        near_puck = np.linalg.norm(pts - puck_xy_fn()[None], axis=1) < PUCK_R + 0.01
        pr = tm.prediction()
        if pr is None:
            return hard
        xs, ys = tm.xs, tm.ys
        step = xs[1] - xs[0]
        r = int(np.ceil(CLEARANCE / step))
        occ = maximum_filter(pr[1] > OCCUPIED, size=2 * r + 1, mode="constant")  # dilate by the clearance
        i = np.rint((pts[:, 0] - xs[0]) / step).astype(int)
        j = np.rint((pts[:, 1] - ys[0]) / step).astype(int)
        # off-grid points: still blocked if the dilated edge reaches them (clip to the nearest cell within r)
        inside = (i >= -r) & (i < len(xs) + r) & (j >= -r) & (j < len(ys) + r)
        out = np.zeros(len(pts), bool)
        out[inside] = occ[np.clip(j[inside], 0, len(ys) - 1), np.clip(i[inside], 0, len(xs) - 1)]
        return (out & ~near_puck) | hard
    return blocked


def route_samples(puck: np.ndarray, angle: float, end: np.ndarray | None) -> np.ndarray:
    """Points along the puck's swept path: centre line and both edges, from just past the puck to its end."""
    u = np.array([np.cos(angle), np.sin(angle)])
    n = np.array([-u[1], u[0]])
    length = SEED_REACH if end is None else max(float((end - puck) @ u), 0.0)
    ts = np.arange(PUCK_R + 0.02, length + PUCK_R + 1e-9, ROUTE_STEP)
    return np.array([puck + t * u + o * n for t in ts for o in (0.0, -PUCK_R, PUCK_R)]).reshape(-1, 2)


def combined_task(sim, tm: TouchMap, agent: PushAgent, ui: dict):
    from src.sim.primitives import probe_down, push, wait

    agent.blocked = make_blocked(tm, lambda: sim.puck_pose()[0])

    # ---- Act 1: map (switch to pushing only between probes, with the arm at safe height) -------------
    ui["phase"] = "MAP"
    while True:
        pr = tm.prediction()
        band = None if pr is None else float(np.mean((pr[2] - pr[0])[tm.mask]))
        ui["status"] = f"mapping: probe {tm.n}/{MAP_PROBES}" + ("" if band is None else f", mean band {band*100:.1f} cm")
        if tm.n >= MAP_PROBES or (band is not None and tm.n >= 15 and band < BAND_DONE):
            while tm.service.busy() or tm.update():
                yield
            break
        puck_xy = sim.puck_pose()[0]
        tm.avoid = [(float(puck_xy[0]), float(puck_xy[1]), PROBE_CLEAR)]
        target = tm.next_target(sim.ctl.tip_pos())
        ui["next"] = target
        res = yield from probe_down(sim, *target)
        # The puck is tracked separately (we push it, so we know where it is): touches on it are not table data.
        if res.contact and np.linalg.norm(np.array([res.x, res.y]) - sim.puck_pose()[0]) > PUCK_R + 0.012:
            tm.add_probe(res.x, res.y, res.height, sim.t)
            ui["probes"].append((res.x, res.y, res.height, res.height > OCCUPIED))
        else:
            tm.skip()
        tm.update()
    ui["log"].append(f"map done after {tm.n} probes; switching to pushing")
    ui["next"] = None

    # ---- Act 2: push around what we found ---------------------------------------------------------
    ui["phase"] = "PUSH"
    checked: list[tuple[float, float]] = []   # spots touched during the push phase (the route is verified there)
    while True:
        puck, _ = sim.puck_pose()
        goal = sim.goal_xy()
        if np.linalg.norm(puck - goal) <= GOAL_TOL:
            ui["plan"], ui["status"] = None, "at goal - move the goal marker"
            yield
            continue
        if not in_workspace(*puck, 0.03):
            ui["plan"], ui["status"] = None, "puck out of reach - drag it back onto the table"
            yield
            continue
        tm.update()
        ui["status"] = "planning around the map"
        p = yield from agent.plan_async(puck, goal)
        if p is None:
            ui["plan"], ui["status"] = None, "no safe push found - move the goal or the puck"
            yield from wait(sim, 1.0)   # re-plan once a second, not every physics step
            continue
        ui["plan"] = (puck.copy(), None if p.predicted_end is None else p.predicted_end.copy(), p.random)
        # Route check: the map is only as fresh as its last touch there (a box may have moved since), so touch
        # the parts of the path nobody has touched during pushing. If anything is in the way, re-plan.
        todo = [q for q in route_samples(puck, p.angle, p.predicted_end)
                if in_workspace(*q) and np.linalg.norm(q - puck) > PROBE_CLEAR
                and not any(np.hypot(q[0] - cx, q[1] - cy) < ROUTE_FRESH for cx, cy in checked)]
        blocked_route = False
        for q in todo[:ROUTE_MAX]:
            ui["status"] = "checking the route by touch"
            ui["next"] = (float(q[0]), float(q[1]))
            res = yield from probe_down(sim, *q)
            checked.append((float(q[0]), float(q[1])))
            if res.contact and np.linalg.norm(np.array([res.x, res.y]) - sim.puck_pose()[0]) > PUCK_R + 0.012:
                ev_p = tm.add_probe(res.x, res.y, res.height, sim.t)
                ui["probes"].append((res.x, res.y, res.height, res.height > OCCUPIED))
                if res.height > OCCUPIED:
                    blocked_route = True
                    ui["log"].append(f"route check: something {res.height*100:.0f} cm tall at "
                                     f"({res.x:.2f}, {res.y:.2f}) - re-planning")
                    break
        ui["next"] = None
        tm.update()   # refresh the learned map in the background; no need to wait for it: a touched obstacle
                      # blocks paths immediately through the raw touches (make_blocked's hard evidence)
        if blocked_route:
            continue                                  # re-plan around what we just touched
        # Only the first ROUTE_MAX unchecked spots (nearest the puck: samples are ordered along the path) are
        # touched before each push. Re-planning until the whole route was checked never ended: early pushes have
        # random aim, so each re-plan brought a new route with new unchecked spots.
        ui["status"] = "seed push (random)" if p.random else "pushing"
        r = yield from push(sim, p.angle, p.offset, p.distance, p.speed)
        ev = agent.observe(p, r.d_push[0], r.d_push[1], r.end_xy, goal)
        ui["pushes"].append({"n": ev.n + 1, "goal_cm": ev.goal_err * 100,
                             "miss_cm": None if ev.miss is None else ev.miss * 100,
                             "spread_cm": None if ev.spread is None else ev.spread * 100, "change": ev.change})
        ui["plan"] = None
        if ev.change:
            # The puck didn't go where we thought: maybe it hit something unmapped. Re-touch along its path.
            ui["log"].append(f"push {ev.n + 1}: puck missed its prediction by {ev.miss*100:.1f} cm - "
                             f"re-mapping {REMAP_PROBES} spots along its path")
            ui["phase"] = "MAP"
            start, end = np.asarray(r.start_xy), np.asarray(r.end_xy)
            for t in np.linspace(0.3, 1.0, REMAP_PROBES):
                x, y = start + t * (end - start) + np.array([0.0, 0.0])
                if not in_workspace(x, y):
                    continue
                if np.linalg.norm(np.array([x, y]) - sim.puck_pose()[0]) < PROBE_CLEAR:
                    continue  # don't probe the puck itself
                ui["next"] = (x, y)
                res = yield from probe_down(sim, x, y)
                if res.contact and np.linalg.norm(np.array([res.x, res.y]) - sim.puck_pose()[0]) > PUCK_R + 0.012:
                    tm.add_probe(res.x, res.y, res.height, sim.t)
                    ui["probes"].append((res.x, res.y, res.height, res.height > OCCUPIED))
                tm.update()
            ui["next"] = None
            ui["phase"] = "PUSH"
