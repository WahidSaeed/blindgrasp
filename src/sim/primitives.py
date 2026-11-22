"""Motion primitives as step-wise generators.

Each generator sets controller goals and `yield`s once per physics step; the caller steps physics
(`env.run(sim, gen)` headless, or `env.run_viewer`). The result is the generator's return value.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.sim.controller import wrap  # noqa: F401
from src.sim.env import PADDLE_HALF_T, PUCK_R, SAFE_Z, TIP_R, Sim

TRANSIT_SPEED = 0.30   # m/s between primitives
APPROACH_SPEED = 0.10  # m/s for the last few cm of a descent
PROBE_SPEED = 0.08     # m/s while feeling for contact (same accuracy as 3 cm/s in eval.phase1_check, ~2x faster)
PUSH_TIP_Z = TIP_R + 0.004  # tip centre height while pushing: tip bottom 4 mm and paddle bottom 10 mm above the table
PUSH_CLEARANCE = 0.03  # minimum gap between paddle face and puck before a push starts
RUNUP_TIME = 0.10      # extra run-up = speed * RUNUP_TIME, so the paddle (which lags its setpoint by
                       # ~0.1 s) is actually at the commanded speed when it reaches the puck


def runup(speed: float) -> float:
    """Gap between paddle face and puck at the start of a push."""
    return PUSH_CLEARANCE + RUNUP_TIME * speed


def move_to(sim: Sim, pos, yaw: float | None = None, speed: float = TRANSIT_SPEED,
            tol: float = 0.004, timeout: float = 6.0, unwrapped: bool = False):
    """Move the tip to `pos` and wait until the setpoint is reached and the tip has caught up."""
    sim.ctl.set_goal(pos, yaw=yaw, speed=speed, unwrapped=unwrapped)
    t_end = sim.t + timeout
    while sim.t < t_end:
        yield
        if sim.ctl.setpoint_reached() and sim.ctl.tracking_error() < tol:
            return True
    return False


def wait(sim: Sim, seconds: float):
    t_end = sim.t + seconds
    while sim.t < t_end:
        yield


# ---- probing ----------------------------------------------------------------------------------------
@dataclass
class ProbeResult:
    x: float           # xy of the highest contact point (tip xy if nothing was touched)
    y: float
    height: float      # surface height (highest contact point), metres above the table top
    force: float       # normal force at detection (N)
    contact: bool      # False if nothing was felt down to the table limit
    duration: float    # sim seconds for the whole primitive


def probe_down(sim: Sim, x: float, y: float, min_force: float = 0.3, max_depth: float = -0.01,
               speed: float = PROBE_SPEED):
    """Go to (x, y) at safe height, descend slowly until contact, record the height, retract."""
    t0 = sim.t
    yield from move_to(sim, (x, y, SAFE_Z))
    sim.ctl.set_goal((x, y, max_depth), speed=speed)
    hit = None
    t_end = sim.t + (SAFE_Z - max_depth) / speed + 2.0
    while sim.t < t_end:
        yield
        hit = sim.probe_contact(min_force)
        if hit is not None:
            break
        # The tip lags the setpoint; keep going until it has actually caught up.
        if sim.ctl.setpoint_reached() and sim.ctl.tracking_error() < 0.002:
            break
    tip = sim.ctl.tip_pos().copy()
    sim.ctl.hold()
    yield from move_to(sim, (x, y, SAFE_Z), speed=APPROACH_SPEED * 2)
    if hit is None:
        return ProbeResult(float(tip[0]), float(tip[1]), float(tip[2] - TIP_R), 0.0, False, sim.t - t0)
    # Report where the touch happened: near a box edge that can be the paddle or rod, not the tip.
    return ProbeResult(float(hit[2]), float(hit[3]), hit[0], hit[1], True, sim.t - t0)


# ---- pushing ----------------------------------------------------------------------------------------
@dataclass
class PushResult:
    angle: float        # push direction in world frame (rad)
    offset: float       # sideways offset of the paddle centre from the puck centre (m, + = left of u)
    distance: float     # commanded travel after first contact (m)
    speed: float        # m/s
    start_xy: np.ndarray
    end_xy: np.ndarray
    d_world: np.ndarray  # (dx, dy) in world frame
    d_push: np.ndarray   # (along, left) in the push frame
    dyaw: float
    tilt: float          # max puck tilt during the push (rad)
    arm_table_contacts: int
    ok: bool             # reached all waypoints, puck upright, no arm-table contact


def push(sim: Sim, angle: float, offset: float, distance: float, speed: float = 0.1, settle_s: float = 2.0):
    """Put the paddle behind the puck, push along `angle` by `distance`, retract, wait for the puck to stop.
    Returns the puck's displacement in world and push frames."""
    p0, yaw0 = sim.puck_pose()
    u = np.array([np.cos(angle), np.sin(angle)])
    n = np.array([-u[1], u[0]])
    gap = runup(speed)
    back = PUCK_R + PADDLE_HALF_T + gap
    start = p0 - u * back + n * offset
    end = start + u * (gap + distance)
    yaw = sim.ctl.paddle_yaw(angle, start)
    contacts0 = sim.contacts.arm_table
    tilt = 0.0

    ok = yield from move_to(sim, (*start, SAFE_Z), yaw=yaw, unwrapped=True)
    ok &= yield from move_to(sim, (*start, PUSH_TIP_Z + 0.03), speed=TRANSIT_SPEED)
    ok &= yield from move_to(sim, (*start, PUSH_TIP_Z), speed=APPROACH_SPEED)
    # Strike: aim the setpoint well past the puck and stop on the *measured* paddle travel, so `speed` is the
    # paddle's real speed at contact and `distance` its real follow-through (the arm lags its setpoint).
    sim.ctl.set_goal((*(end + u * 0.15), PUSH_TIP_Z), speed=speed)
    t_end = sim.t + (gap + distance) / speed + 3.0
    while sim.t < t_end:
        yield
        tilt = max(tilt, sim.puck_tilt())
        if (sim.ctl.tip_pos()[:2] - start) @ u >= gap + distance:
            sim.ctl.hold()
            break
    else:
        ok = False
    yield from wait(sim, 0.15)
    end = sim.ctl.tip_pos()[:2].copy()
    # Back off 1 cm before lifting so the paddle doesn't drag the puck.
    back_off = end - u * 0.01
    yield from move_to(sim, (*back_off, PUSH_TIP_Z), speed=APPROACH_SPEED)
    yield from move_to(sim, (*back_off, SAFE_Z), speed=TRANSIT_SPEED)

    t_end = sim.t + settle_s
    still = 0
    while sim.t < t_end and still < 50:
        yield
        tilt = max(tilt, sim.puck_tilt())
        still = still + 1 if sim.obj_speed("puck") < 1e-3 else 0

    p1, yaw1 = sim.puck_pose()
    d = p1 - p0
    arm_hits = sim.contacts.arm_table - contacts0
    return PushResult(
        angle=angle, offset=offset, distance=distance, speed=speed, start_xy=p0, end_xy=p1,
        d_world=d, d_push=np.array([d @ u, d @ n]), dyaw=wrap(yaw1 - yaw0), tilt=tilt,
        arm_table_contacts=arm_hits, ok=bool(ok and tilt < 0.3 and arm_hits == 0),
    )
