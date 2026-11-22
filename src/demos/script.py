"""Scripted presenter mode: the combined demo with fixed seeds and the interrupts from the build plan
fired at fixed points in the run, so the live demo plays out the same way every time.

Beats (triggered by progress, not by the clock, so a slow learner just stretches the timeline):
  1. map by touch                                  - the arm probes the most uncertain spots
  2. after MOVE_BOX_AT probes: presenter moves a    - the map still says that spot is clear ...
     box onto the puck's route
  3. map done -> push the puck to the goal           - ... until the route check touches it; the puck goes around
  4. at goal: table turns icy, goal moves            - first push overshoots, change detected, re-adapts
  5. done                                           - idles at the goal

Live: python -m src.web.server --mode script
Physics and the robot's choices are seeded; with a background learner the exact probe sequence can still
shift if a fit finishes a frame earlier or later, but the story beats always happen in this order.
"""
from __future__ import annotations

import numpy as np

from src.demos.combined import combined_task
from src.demos.push import GOAL_TOL

SEED = 7
MOVE_BOX_AT = 25
BOX_MOVE = ("box_c", (0.53, 0.06), 0.06)           # (box, new xy, half height): on the straight puck route
PUCK_START, GOAL_1 = (0.40, -0.02), (0.66, 0.02)
GOAL_ICY = (0.42, -0.14)                           # long open run: on ice the first push overshoots
RECOVER_XY = (0.46, 0.0)                           # where the presenter puts a puck that slid out of reach


def clear_spot(blocked, puck, goal):
    """Nearest point to the puck (ties broken towards the goal) whose puck footprint is clear on the map."""
    from src.sim.env import PUCK_R, in_workspace

    ring = np.linspace(0, 2 * np.pi, 16, endpoint=False)
    rim = np.column_stack([np.cos(ring), np.sin(ring)]) * (PUCK_R + 0.01)
    for r in np.arange(0.03, 0.15, 0.01):
        cands = puck + r * np.column_stack([np.cos(ring), np.sin(ring)])
        cands = cands[np.argsort(np.linalg.norm(cands - goal, axis=1))]
        for c in cands:
            if (in_workspace(*c, 0.04) and np.linalg.norm(c - goal) > 0.05   # never "nudge" it into the goal
                    and not blocked(np.vstack([c, c + rim])).any()):
                return c
    return None


def scripted_task(sim, tm, agent, ui):
    """Wraps combined_task and injects the presenter's actions."""
    sim.place("puck", *PUCK_START, 0.02)
    ui["puck_told"] = PUCK_START          # the task says where the puck starts; after that the robot finds it by touch
    sim.set_goal_xy(*GOAL_1)
    ui["beat"] = "1 · map by touch"
    inner = combined_task(sim, tm, agent, ui)
    moved_box = False
    goals_done = 0
    at_goal_prev = False
    out_since = None
    jam_since = None
    last_n_push = 0
    while True:
        next(inner)
        yield
        if not moved_box and tm.n >= MOVE_BOX_AT and sim.ctl.tip_pos()[2] > 0.15:  # arm up, not touching
            name, xy, hz = BOX_MOVE
            sim.place(name, *xy, hz)
            ui["log"].append(f"PRESENTER: moved {name} onto the puck's route ({xy[0]:.2f}, {xy[1]:.2f})")
            ui["beat"] = "2 · presenter moved a box onto the route"
            moved_box = True
        if ui.get("phase") == "PUSH" and ui["beat"].startswith(("1", "2")):
            ui["beat"] = "3 · push the puck to the goal"
        # The robot decides it is at the goal from where it *felt* the puck; the log also shows the simulator's
        # true distance, as a check that the touch estimate is honest.
        at_goal = ui.get("phase") == "PUSH" and ui.get("status", "").startswith("at goal")
        if at_goal and not at_goal_prev:
            goals_done += 1
            b = ui["belief"].xy
            d_est = np.linalg.norm(b - sim.goal_xy())
            d_true = np.linalg.norm(sim.puck_pose()[0] - sim.goal_xy())
            ui["log"].append(f"goal {goals_done} reached: robot feels the puck {d_est*100:.1f} cm from the goal "
                             f"[simulator: {d_true*100:.1f} cm]")
            if goals_done == 1:
                sim.set_friction("low")
                sim.set_goal_xy(*GOAL_ICY)
                ui["log"].append("PRESENTER: the table is now icy; goal moved")
                ui["beat"] = "4 · icy table: adapt in a few pushes"
            elif goals_done == 2:
                ui["log"].append("script finished")
                ui["beat"] = "5 · done"
        at_goal_prev = at_goal
        # A puck that slid out of reach would stall the show: after 2 s the "presenter" puts it back.
        if ui.get("status", "").startswith(("puck out of reach", "lost the puck")):
            out_since = sim.t if out_since is None else out_since
            if sim.t - out_since > 2.0 and sim.ctl.tip_pos()[2] > 0.15:
                sim.place("puck", *RECOVER_XY, 0.02)
                ui["puck_told"] = RECOVER_XY
                ui["log"].append("PRESENTER: put the puck back on the table and told the robot where")
                out_since = None
        else:
            out_since = None
        # Jammed (planning keeps finding no safe push, e.g. the puck is wedged against a box): nudge it to the
        # nearest clear spot. The timer runs from the last push, since the status flips between "planning" and
        # "no safe push" on every attempt.
        n_push = len(ui["pushes"])
        if n_push != last_n_push or ui.get("phase") != "PUSH" or ui.get("status", "").startswith(("at goal", "pushing")):
            last_n_push, jam_since = n_push, None
        elif ui.get("status", "").startswith("no safe push") and agent.blocked is not None:
            jam_since = sim.t if jam_since is None else jam_since
            if sim.t - jam_since > 5.0 and sim.ctl.tip_pos()[2] > 0.15:
                spot = clear_spot(agent.blocked, sim.puck_pose()[0], sim.goal_xy())   # the presenter can see
                if spot is not None:
                    sim.place("puck", *spot, 0.02)
                    ui["puck_told"] = tuple(spot)
                    ui["log"].append(f"PRESENTER: puck was wedged - nudged it to ({spot[0]:.2f}, {spot[1]:.2f}) "
                                     "and told the robot")
                jam_since = None
