"""Headless Demo 2 evaluation with real physics pushes.

Per seed: a sequence of goals with normal physics (context starts empty), then a physics change
(friction low/high or mass light/heavy) and more goals. Reports pushes needed to get within 3 cm.

    python -m eval.push_eval --learners gp knn mlp tabpfn --adapt reset window none --seeds 10
    python -m eval.push_eval --learners tabpfn gp --sense touch     # the robot finds the puck by touch

--sense touch: the robot only knows where the puck starts; after every push it feels for it (src/demos/puck_search.py)
and learns from where it found it. --sense oracle (the old behaviour): positions come from the simulator.
"Reached" is always scored against the simulator's true puck position.
"""
from __future__ import annotations

import argparse
import json
import time
import warnings
from pathlib import Path

import numpy as np

from src.demos.puck_search import PuckBelief
from src.demos.push import GOAL_TOL, PushAgent, execute_push
from src.learn.baselines import learner_kwargs
from src.sim.env import Sim, in_workspace, run
from src.sim.primitives import push

warnings.filterwarnings("ignore")
OUT = Path(__file__).resolve().parent / "out"
# Mass is not in the list: the paddle is position-controlled (the arm doesn't slow down for a heavier puck) and a
# sliding puck's stopping distance v^2 / (2 mu g) doesn't depend on mass, so heavy/light change travel by < 0.6 cm:
# there is nothing to adapt to. Measured travel at 0.15/0.30/0.45 m/s: normal 2.5/3.2/4.4 cm, icy 3.6/7.8/14.0,
# high friction 2.2/1.6/1.2, heavy 2.6/3.6/4.8, light 2.4/4.2/4.8.
CHANGES = [("friction", "low"), ("friction", "high")]


def sample_goal(rng, puck):
    for _ in range(1000):
        g = rng.uniform([0.30, -0.28], [0.66, 0.28])
        if in_workspace(*g, 0.06) and 0.10 <= np.linalg.norm(g - puck) <= 0.25:
            return g
    return np.array([0.48, 0.0])


def run_seed(learner, adapt, seed, goals_before, goals_after, max_pushes, kappa, change=None,
             n_estimators=None, sense="oracle") -> dict:
    rng = np.random.default_rng(seed)
    sim = Sim()
    for i, b in enumerate(("box_a", "box_b", "box_c")):
        sim.place(b, 2.0 + 0.3 * i, 0.0)
    sim.place("puck", 0.46, 0.0, 0.02)
    sim.settle(0.3)
    agent = PushAgent(learner, adapt, kappa=kappa, seed=seed, learner_kwargs=learner_kwargs(learner, n_estimators))
    change = change or CHANGES[seed % len(CHANGES)]
    belief = PuckBelief()
    belief.tell(sim.puck_pose()[0])          # the task says where the puck starts
    ui = {"log": [], "pushes": [], "status": "", "plan": None, "next": None}
    episodes = []
    for gi in range(goals_before + goals_after):
        if gi == goals_before:
            (sim.set_friction if change[0] == "friction" else sim.set_mass)(change[1])
        puck, _ = sim.puck_pose()
        if not in_workspace(*puck, 0.05) or not belief.known:  # recover a puck pushed to the edge (or lost)
            sim.place("puck", 0.46, 0.0, 0.02)
            sim.settle(0.3)
            puck, _ = sim.puck_pose()
            belief.tell(puck)                # whoever put it back tells the robot
        goal = sample_goal(rng, puck)
        sim.set_goal_xy(*goal)
        errs, changes, misses, touches, loc_err = [], [], [], [], []
        for _ in range(max_pushes):
            puck = belief.xy if sense == "touch" else sim.puck_pose()[0]
            if np.linalg.norm(puck - goal) <= GOAL_TOL:
                break
            p = agent.plan(puck, goal)
            if p is None:
                for f in (agent.svc_along.pending, agent.svc_left.pending):
                    if f is not None and f.done() and f.exception() is not None:
                        raise RuntimeError(f"{learner} fit failed (not a planning result)") from f.exception()
                break
            if sense == "touch":
                r, ev, s = run(sim, execute_push(sim, agent, p, belief, goal, ui), max_seconds=300)
                touches.append(s.n)
                if s.xy is not None:
                    loc_err.append(float(np.linalg.norm(s.xy - r.true_end_xy)))
                if ev is None:
                    if not belief.known:
                        break
                    continue
            else:
                r = run(sim, push(sim, p.angle, p.offset, p.distance, p.speed, puck))
                d = r.true_d_push
                ev = agent.observe(p, d[0], d[1], r.true_end_xy, goal)
            errs.append(float(np.linalg.norm(sim.puck_pose()[0] - goal)))   # scored on the true position
            misses.append(ev.miss)
            changes.append(ev.change)
        puck, _ = sim.puck_pose()
        done = np.linalg.norm(puck - goal) <= GOAL_TOL
        episodes.append({"goal": gi, "after_change": gi >= goals_before, "pushes": len(errs), "reached": bool(done),
                         "final_err": float(np.linalg.norm(puck - goal)), "errs": errs, "changes": changes, "misses": misses,
                         "touches": touches, "loc_err": loc_err})
    agent.shutdown()
    return {"learner": learner, "adapt": adapt, "seed": seed, "change": list(change), "sense": sense, "episodes": episodes}


def summarize(results):
    groups = {}
    for r in results:
        groups.setdefault((r["learner"], r["adapt"]), []).append(r)
    print(f"\n{'learner':8s} {'adapt':7s} | first goal (empty ctx): reached / pushes | later goals | "
          f"first goal after change: reached / pushes | detected change")
    for (lr, ad), rs in sorted(groups.items()):
        first = [r["episodes"][0] for r in rs]
        later = [e for r in rs for e in r["episodes"][1:] if not e["after_change"]]
        after = [next(e for e in r["episodes"] if e["after_change"]) for r in rs]
        det = [any(any(e["changes"]) for e in r["episodes"] if e["after_change"]) for r in rs]
        false = [any(any(e["changes"]) for e in r["episodes"] if not e["after_change"]) for r in rs]
        f = lambda es: f"{np.mean([e['reached'] for e in es])*100:3.0f}% / {np.median([e['pushes'] for e in es]):4.1f}"  # noqa: E731
        print(f"{lr:8s} {ad:7s} | {f(first):>22s}               | {f(later):>11s} | {f(after):>27s}              | "
              f"{np.mean(det)*100:3.0f}% (false before: {np.mean(false)*100:.0f}%)")
        seq = [t for r in rs for e in r["episodes"] for t in e.get("touches", [])]
        if seq:
            # Touches to find the puck, by push number within each run (do they drop as the push model learns?)
            by_k: dict = {}
            for r in rs:
                k = 0
                for e in r["episodes"]:
                    for t in e["touches"]:
                        by_k.setdefault(k, []).append(t)
                        k += 1
            le = [x for r in rs for e in r["episodes"] for x in e["loc_err"]]
            print(f"{'':17s}  touches to find the puck: median {np.median(seq):.0f} per push; by push number "
                  + " ".join(f"{k + 1}:{np.median(v):.0f}" for k, v in sorted(by_k.items())[:12])
                  + f" | touch estimate vs true: median {np.median(le)*1000:.1f} mm, max {np.max(le)*1000:.1f} mm")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--learners", nargs="+", default=["gp", "knn"])
    ap.add_argument("--adapt", nargs="+", default=["reset"])
    ap.add_argument("--seeds", type=int, default=4)
    ap.add_argument("--goals-before", type=int, default=3)
    ap.add_argument("--goals-after", type=int, default=2)
    ap.add_argument("--max-pushes", type=int, default=12)
    ap.add_argument("--kappa", type=float, default=1.0)
    ap.add_argument("--tag", default="push")
    ap.add_argument("--change", nargs=2, default=None, metavar=("KIND", "LEVEL"),
                    help="use this change for every seed, e.g. --change friction low")
    ap.add_argument("--n-estimators", type=int, default=None, help="TabPFN ensemble size")
    ap.add_argument("--sense", default="oracle", choices=["oracle", "touch"], help="how the robot knows where the puck is")
    args = ap.parse_args()
    t0 = time.perf_counter()
    results = []
    for lr in args.learners:
        for ad in args.adapt:
            for s in range(args.seeds):
                results.append(run_seed(lr, ad, s, args.goals_before, args.goals_after, args.max_pushes, args.kappa,
                                        change=tuple(args.change) if args.change else None,
                                        n_estimators=args.n_estimators, sense=args.sense))
            print(f"done {lr}/{ad} ({time.perf_counter() - t0:.0f}s)", flush=True)
    OUT.mkdir(exist_ok=True)
    (OUT / f"{args.tag}.json").write_text(json.dumps(results))
    summarize(results)


if __name__ == "__main__":
    main()
