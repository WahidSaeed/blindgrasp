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
    ap.add_argument("--clean", action="store_true", help="no caption bar (for editing)")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--views", default="front", help="comma list of front,top,side,hero; one video per view")
    ap.add_argument("--events", default=None, help="write a per-frame JSON log (beat, probes, pushes, log lines)")
    args = ap.parse_args()
    out = Path(args.out or f"eval/out/clips/{args.mode}_{args.learner}.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)

    sim = Sim()
    sim.settle(0.3)
    lk = learner_kwargs(args.learner, args.n_estimators)
    seed = args.seed if args.seed is not None else (SCRIPT_SEED if args.mode == "script" else 0)
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

    sim.model.vis.global_.offwidth = max(sim.model.vis.global_.offwidth, args.width)
    sim.model.vis.global_.offheight = max(sim.model.vis.global_.offheight, args.height)
    renderer = mujoco.Renderer(sim.model, args.height, args.width, max_geom=10000)
    presets = {"front": (1.35, 180, -40), "top": (1.25, 180, -89), "side": (1.4, 240, -30), "hero": (1.05, 215, -24)}
    views = [v.strip() for v in args.views.split(",") if v.strip()]
    cams = {}
    for v in views:
        c = mujoco.MjvCamera()
        c.lookat[:] = (0.45, 0.0, 0.02) if v != "hero" else (0.5, 0.0, 0.05)
        c.distance, c.azimuth, c.elevation = presets[v]
        cams[v] = c
    cam = cams[views[0]]
    ov = Overlay(tm.xs, tm.ys)
    steps_per_frame = max(1, round(args.speed / args.fps / sim.model.opt.timestep))
    log_lines: list[str] = []
    outs = {v: (out if i == 0 else out.with_name(f"{out.stem}_{v}{out.suffix}")) for i, v in enumerate(views)}
    writers = {v: imageio.get_writer(o, fps=args.fps, codec="libx264", quality=9, macro_block_size=8) for v, o in outs.items()}
    writer = writers[views[0]]
    events: list[dict] = []
    all_log: list[str] = []
    t0, frames = time.perf_counter(), 0
    end_t = None
    acted = 0          # map/push clips: scripted interrupt (box move / icy table) already done?
    goals_hit = 0
    ev_seen = 0
    try:
        while sim.t < args.max_sim:
            for _ in range(steps_per_frame):
                next(task)
                sim.step()
            if args.mode != "push":
                tm.wait()   # deterministic: the robot always sees the newest map
                # Same change-detection log lines as the web viewer (src/web/server.py _track_events).
                for ev in tm.events[ev_seen:]:
                    if ev.confirmed:
                        ui["log"].append(f"probe {ev.n + 1}: CHANGE CONFIRMED - now reads {ev.height*100:.1f} cm; dropped {ev.dropped} stale rows")
                    elif ev.surprise and ev.verify:
                        ui["log"].append(f"probe {ev.n + 1}: surprise - felt {ev.height*100:.1f} cm, map said {ev.predicted*100:.1f} cm; re-checking an old point")
                ev_seen = len(tm.events)
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
            new_log = []
            while ui["log"]:
                ln = ui["log"].pop(0)
                new_log.append(ln)
                log_lines = (log_lines + [ln])[-2:]
            pr = tm.prediction() if args.mode != "push" else None
            plan = ui.get("plan")

            def draw(c):
                renderer.update_scene(sim.data, camera=c)
                if pr is not None:
                    ov.draw(renderer.scene, height=pr[1], band=pr[2] - pr[0], probes=ui["probes"],
                            next_target=ui["next"], mask=tm.mask, clear=False)
                if plan is not None and plan[1] is not None:
                    ov.draw(renderer.scene, path=[tuple(plan[0]), tuple(plan[1])], path_ok=not plan[2], clear=False)
                return renderer.render()
            stats = f"{args.learner} | probes {tm.n} | pushes {len(ui['pushes'])} | sim {sim.t:5.0f}s"
            if ui["pushes"]:
                stats += f" | goal dist {ui['pushes'][-1]['goal_cm']:.1f} cm"
            head = ui.get("beat") or {"map": "Act 1: map by touch", "push": "Act 2: few-shot pushing",
                                       "combined": "Acts 1 + 2"}.get(args.mode, "")
            for v in views[1:]:
                img = draw(cams[v])
                writers[v].append_data(img if args.clean else caption(img, [f"{head}   ·   {ui.get('status', '')}", stats] + log_lines))
            img = draw(cam)
            writer.append_data(img if args.clean else caption(img, [f"{head}   ·   {ui.get('status', '')}", stats] + log_lines))
            if args.events is not None:
                p = ui["pushes"][-1] if ui["pushes"] else None
                events.append({"f": frames, "t": round(sim.t, 3), "beat": ui.get("beat", ""), "status": ui.get("status", ""),
                               "probes": tm.n, "pushes": len(ui["pushes"]), "goal_cm": None if p is None else round(p["goal_cm"], 2),
                               "fit": tm.n and pr is not None, "log": new_log})
            frames += 1
            if args.mode == "script" and str(ui.get("beat", "")).startswith("5"):
                # keep running 3 s of sim so the last push's result reaches the caption, then hold 2 s
                end_t = end_t or sim.t + 3.0
                if sim.t >= end_t:
                    for _ in range(args.fps * 2):
                        for v in views:
                            img = draw(cams[v])
                            writers[v].append_data(img if args.clean else caption(img, ["5 · done", stats] + log_lines))
                    break
    finally:
        for w in writers.values():
            w.close()
        if args.events is not None:
            import json
            Path(args.events).write_text(json.dumps({"fps": args.fps, "speed": args.speed, "frames": events}))
        tm.service.shutdown()
        agent.shutdown()
    print(f"wrote {out}: {frames / args.fps:.0f} s of video, {sim.t:.0f} s sim, {time.perf_counter() - t0:.0f} s wall")


if __name__ == "__main__":
    main()
