"""Render MP4 fallback clips of the demo (offscreen, same view and overlay as the browser viewer).

    python -m eval.render_clips --mode script --learner gp --speed 6 --out eval/out/clips/script.mp4
    python -m eval.render_clips --mode map  --learner tabpfn --n-estimators 1 --pred-step 0.04

Fits run synchronously here (the sim waits for each prediction), so the clip is deterministic for a given
learner and seed, and a slow learner doesn't show up as lag. A caption bar shows the act, beat and stats.
"""
from __future__ import annotations

import argparse
import time
import warnings
from pathlib import Path

import imageio.v2 as imageio
import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from src.demos.combined import combined_task
from src.demos.push import PushAgent, pushing_task
from src.demos.script import SEED as SCRIPT_SEED
from src.demos.script import scripted_task
from src.demos.touch_map import TouchMap, mapping_task
from src.learn.baselines import learner_kwargs
from src.sim.env import Sim
from src.viz.overlay import Overlay

warnings.filterwarnings("ignore")


def caption(img: np.ndarray, lines: list[str]) -> np.ndarray:
    im = Image.fromarray(img)
    d = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
    except OSError:
        font = ImageFont.load_default()
    h = 12 + 26 * len(lines)
    d.rectangle([0, 0, im.width, h], fill=(15, 18, 22))
    for i, t in enumerate(lines):
        d.text((14, 8 + 26 * i), t, fill=(230, 233, 238), font=font)
    return np.asarray(im)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="script", choices=["map", "push", "combined", "script"])
    ap.add_argument("--learner", default="gp", choices=["tabpfn", "tabpfn_nn", "gp", "knn", "mlp"])
    ap.add_argument("--n-estimators", type=int, default=None)
    ap.add_argument("--pred-step", type=float, default=None)
    ap.add_argument("--speed", type=float, default=6.0, help="sim seconds per video second")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--max-sim", type=float, default=600.0, help="stop after this much sim time")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out = Path(args.out or f"eval/out/clips/{args.mode}_{args.learner}.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)

    sim = Sim()
    sim.settle(0.3)
    lk = learner_kwargs(args.learner, args.n_estimators)
    seed = SCRIPT_SEED if args.mode == "script" else 0
    tm = TouchMap(args.learner, "active", seed=seed, learner_kwargs=lk, pred_step=args.pred_step)
    agent = PushAgent(args.learner, "reset", seed=seed, learner_kwargs=lk)
    ui = {"probes": [], "next": None, "plan": None, "pushes": [], "log": [], "status": "", "beat": ""}
    if args.mode == "push":
        for i, b in enumerate(("box_a", "box_c")):
            sim.place(b, 0.20, 0.15 if i == 0 else -0.15, 0.04 if i == 0 else 0.06)
        sim.place("box_b", 0.68, 0.37, 0.03)
        sim.place("puck", 0.42, -0.05, 0.02)
        sim.set_goal_xy(0.60, 0.10)
        task = pushing_task(sim, agent, ui)
    elif args.mode == "map":
        task = mapping_task(sim, tm, ui)
    elif args.mode == "combined":
        sim.place("puck", 0.45, 0.0, 0.02)
        sim.set_goal_xy(0.66, 0.05)
        task = combined_task(sim, tm, agent, ui)
    else:
        task = scripted_task(sim, tm, agent, ui)

    renderer = mujoco.Renderer(sim.model, args.height, args.width, max_geom=10000)
    cam = mujoco.MjvCamera()
    cam.lookat[:] = (0.45, 0.0, 0.02)
    cam.distance, cam.azimuth, cam.elevation = 1.35, 180, -40
    ov = Overlay(tm.xs, tm.ys)
    steps_per_frame = max(1, round(args.speed / args.fps / sim.model.opt.timestep))
    log_lines: list[str] = []
    writer = imageio.get_writer(out, fps=args.fps, codec="libx264", quality=8, macro_block_size=8)
    t0, frames = time.perf_counter(), 0
    end_t = None
    acted = 0          # map/push clips: scripted interrupt (box move / icy table) already done?
    goals_hit = 0
    try:
        while sim.t < args.max_sim:
            for _ in range(steps_per_frame):
                next(task)
                sim.step()
            if args.mode != "push":
                tm.wait()   # deterministic: the robot always sees the newest map
            # Act clips get their interrupt from the plan: Act 1 a moved box, Act 2 an icy table.
            if args.mode == "map" and not acted and tm.n >= 30 and sim.ctl.tip_pos()[2] > 0.15:
                sim.place("box_c", 0.45, -0.20, 0.06)
                ui["log"].append("PRESENTER: moved the pink box to (0.45, -0.20)")
                ui["beat"], acted = "Act 1 · a box was moved: probes contradict the map", 1
            if args.mode == "map" and tm.n >= 60:
                end_t = end_t or sim.t + 2.0
                if sim.t >= end_t:
                    break
            if args.mode == "push":
                at = (sim.obj_speed("puck") < 0.005
                      and np.linalg.norm(sim.puck_pose()[0] - sim.goal_xy()) <= 0.03)
                if at and goals_hit == 0:
                    goals_hit = 1
                    sim.set_friction("low")
                    sim.set_goal_xy(0.42, -0.12)
                    ui["log"].append("PRESENTER: the table is now icy; goal moved")
                    ui["beat"] = "Act 2 · icy table: first push overshoots, then it re-adapts"
                elif at and goals_hit == 1 and sim.t > 5:
                    end_t = end_t or sim.t + 3.0
                    ui["beat"] = "Act 2 · back on target"
                    if sim.t >= end_t:
                        break
            while ui["log"]:
                log_lines = (log_lines + [ui["log"].pop(0)])[-2:]
            renderer.update_scene(sim.data, camera=cam)
            pr = tm.prediction() if args.mode != "push" else None
            if pr is not None:
                ov.draw(renderer.scene, height=pr[1], band=pr[2] - pr[0], probes=ui["probes"],
                        next_target=ui["next"], mask=tm.mask, clear=False)
            plan = ui.get("plan")
            if plan is not None and plan[1] is not None:
                ov.draw(renderer.scene, path=[tuple(plan[0]), tuple(plan[1])], path_ok=not plan[2], clear=False)
            stats = f"{args.learner} | probes {tm.n} | pushes {len(ui['pushes'])} | sim {sim.t:5.0f}s"
            if ui["pushes"]:
                stats += f" | goal dist {ui['pushes'][-1]['goal_cm']:.1f} cm"
            head = ui.get("beat") or {"map": "Act 1: map by touch", "push": "Act 2: few-shot pushing",
                                       "combined": "Acts 1 + 2"}.get(args.mode, "")
            writer.append_data(caption(renderer.render(), [f"{head}   ·   {ui.get('status', '')}", stats] + log_lines))
            frames += 1
            if args.mode == "script" and str(ui.get("beat", "")).startswith("5"):
                # keep running 3 s of sim so the last push's result reaches the caption, then hold 2 s
                end_t = end_t or sim.t + 3.0
                if sim.t >= end_t:
                    for _ in range(args.fps * 2):
                        writer.append_data(caption(renderer.render(), ["5 · done", stats] + log_lines))
                    break
    finally:
        writer.close()
        tm.service.shutdown()
        agent.shutdown()
    print(f"wrote {out}: {frames / args.fps:.0f} s of video, {sim.t:.0f} s sim, {time.perf_counter() - t0:.0f} s wall")


if __name__ == "__main__":
    main()
