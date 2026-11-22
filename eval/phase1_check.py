"""Phase 1 acceptance: 100 random probes vs ray cast (within 3 mm), 100 random pushes (no flip, no arm-table hit).

    python -m eval.phase1_check [--probes 100] [--pushes 100] [--probe-speed 0.03] [--seed 0]
"""
from __future__ import annotations

import argparse
import time

import numpy as np

from src.sim.env import WORKSPACE_X, WORKSPACE_Y, Sim, in_workspace, run
from src.sim.primitives import PADDLE_HALF_T, PUCK_R, probe_down, push, runup


def check_probes(n: int, speed: float, rng: np.random.Generator) -> bool:
    sim = Sim(); sim.settle(0.3)
    errs, errs_local, near_edge, missed, durs = [], [], [], 0, []
    for _ in range(n):
        while True:
            x, y = rng.uniform(*WORKSPACE_X), rng.uniform(*WORKSPACE_Y)
            if in_workspace(x, y):
                break
        r = run(sim, probe_down(sim, x, y, speed=speed))
        if not r.contact:
            missed += 1
            continue
        truth = sim.true_height(r.x, r.y)
        errs.append(abs(r.height - truth))
        # An edge contact sits on the box boundary, where a ray can just miss the box. Also score against
        # the closest surface height within 3 mm horizontally of the contact point.
        local = [sim.true_height(r.x + rr * np.cos(a), r.y + rr * np.sin(a))
                 for rr in (0.0015, 0.003) for a in np.linspace(0, 2 * np.pi, 12, endpoint=False)]
        errs_local.append(min(abs(r.height - truth), *(abs(r.height - h) for h in local)))
        durs.append(r.duration)
        # Does the 6 mm tip sphere straddle a height step? (truth differs within its radius)
        ring = [sim.true_height(r.x + 0.007 * np.cos(a), r.y + 0.007 * np.sin(a)) for a in np.linspace(0, 2 * np.pi, 8, endpoint=False)]
        near_edge.append(max(ring) - min(ring) > 0.003)
    e = np.array(errs) * 1000
    ne = np.array(near_edge)
    within = np.mean(e <= 3.0)
    print(f"probes @ {speed*100:.0f} cm/s: n={len(e)} missed={missed} | within 3 mm: {within*100:.0f}% "
          f"| median {np.median(e):.2f} mm, max {e.max():.1f} mm | mean duration {np.mean(durs):.2f} s sim")
    if ne.any():
        print(f"   near a height step: {ne.sum()} probes, within 3 mm {np.mean(e[ne] <= 3)*100:.0f}%; "
              f"away from steps: within 3 mm {np.mean(e[~ne] <= 3)*100:.0f}%")
    el = np.array(errs_local) * 1000
    print(f"   vs surface within 3 mm of the contact point: within 3 mm {np.mean(el <= 3)*100:.0f}%, max {el.max():.1f} mm")
    print(f"   probe/table contacts ok; arm-table contacts: {sim.contacts.arm_table}; boxes moved: "
          + ", ".join(f"{b} {np.linalg.norm(sim.body_pos(b)[:2]-p)*1000:.1f}mm" for b, p in BOX_HOME.items()))
    return bool(np.all(el <= 3.0)) and missed == 0 and sim.contacts.arm_table == 0


BOX_HOME = {"box_a": np.array([0.38, 0.22]), "box_b": np.array([0.60, -0.24]), "box_c": np.array([0.63, 0.18])}


def check_pushes(n: int, rng: np.random.Generator) -> bool:
    sim = Sim()
    for b in BOX_HOME:  # clear the table so random pushes don't run into boxes
        sim.place(b, 2.0 + list(BOX_HOME).index(b) * 0.3, 0.0)
    sim.settle(0.3)
    margin = 0.02
    res = []
    for _ in range(n):
        while True:
            px, py = rng.uniform(0.30, 0.62), rng.uniform(-0.25, 0.25)
            a, off = rng.uniform(-np.pi, np.pi), rng.uniform(-0.015, 0.015)
            dist, speed = rng.uniform(0.02, 0.08), rng.uniform(0.05, 0.15)
            u = np.array([np.cos(a), np.sin(a)]); nrm = np.array([-u[1], u[0]])
            back = PUCK_R + PADDLE_HALF_T + runup(speed)
            start = np.array([px, py]) - u * back + nrm * off
            end = start + u * (runup(speed) + dist)
            pts = np.array([start, end, np.array([px, py]) + u * (dist + PUCK_R)])
            if all(in_workspace(*p, margin=margin) for p in pts):
                break
        sim.place("puck", px, py, 0.02, rng.uniform(-np.pi, np.pi))
        res.append(run(sim, push(sim, a, off, dist, speed, (px, py))))  # motion test: true start
    for i, r in enumerate(res):
        if not r.ok:
            print(f"   push {i} not ok: angle {np.degrees(r.angle):.0f} deg, puck {np.round(r.start_xy, 3)}, "
                  f"tilt {r.tilt:.2f}, arm hits {r.arm_table_contacts}, moved {np.round(r.true_d_push * 1000, 1)} mm "
                  f"(waypoint timeout if tilt/hits are fine)")
    ok = np.array([r.ok for r in res])
    tilt = np.array([r.tilt for r in res])
    hits = sum(r.arm_table_contacts for r in res)
    along = np.array([r.true_d_push[0] / r.distance for r in res])
    side = np.abs([r.true_d_push[1] for r in res]) * 1000
    print(f"pushes: n={n} ok={ok.sum()} | flips (tilt>0.3 rad)={np.sum(tilt > 0.3)} max tilt {tilt.max():.3f} rad "
          f"| arm-table contacts={hits}")
    print(f"   travel/commanded: median {np.median(along):.2f} (min {along.min():.2f}, max {along.max():.2f}); "
          f"sideways drift median {np.median(side):.1f} mm, max {side.max():.1f} mm")
    return bool(ok.all())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probes", type=int, default=100)
    ap.add_argument("--pushes", type=int, default=100)
    ap.add_argument("--probe-speed", type=float, nargs="+", default=[0.08])
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    t0 = time.perf_counter()
    passed = True
    for s in args.probe_speed:
        if args.probes:
            passed &= check_probes(args.probes, s, np.random.default_rng(args.seed))
    if args.pushes:
        passed &= check_pushes(args.pushes, np.random.default_rng(args.seed))
    print(f"{'PASS' if passed else 'FAIL'}  ({time.perf_counter() - t0:.0f} s wall)")


if __name__ == "__main__":
    main()
