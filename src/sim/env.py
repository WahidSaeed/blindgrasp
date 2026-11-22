"""Scene wrapper: model/data, one-call stepping, contact queries, ground truth, runtime physics changes,
and a real-time passive viewer loop that drives a primitive/task generator.

On macOS the viewer must be started with `mjpython` (e.g. `.venv/bin/mjpython -m src.demos.touch_map`).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Generator, Iterable

import mujoco
import numpy as np

from src.config import ROOT
from src.sim.controller import Controller

SCENE_XML = ROOT / "assets" / "scene.xml"

# Tested workspace for the probe tip: a box clipped to a ring around the base. Inside 0.32 m the elbow
# (joint 4) folds onto its limit and tracking degrades; beyond ~0.80 m the arm runs out of reach.
WORKSPACE_X = (0.20, 0.72)
WORKSPACE_Y = (-0.35, 0.35)
WORKSPACE_R = (0.32, 0.80)


def in_workspace(x: float, y: float, margin: float = 0.0) -> bool:
    r = float(np.hypot(x, y))
    return (WORKSPACE_X[0] + margin <= x <= WORKSPACE_X[1] - margin
            and WORKSPACE_Y[0] + margin <= y <= WORKSPACE_Y[1] - margin
            and WORKSPACE_R[0] + margin <= r <= WORKSPACE_R[1] - margin)
TABLE_X = (0.15, 0.75)
TABLE_Y = (-0.40, 0.40)
SAFE_Z = 0.18          # transit height of the tip centre (tallest box is 0.12 m)
TIP_R = 0.006          # probe tip sphere radius
PADDLE_HALF_T = 0.004  # paddle half-thickness along its normal
PUCK_R = 0.035
PUCK_HALF_H = 0.02

FRICTION_LEVELS = {"normal": 0.5, "low": 0.08, "high": 1.0}  # cycle order: first press = icy
MASS_LEVELS = {"normal": 0.2, "heavy": 0.8, "light": 0.1}  # cycle order: first press = heavy

OBJECTS = ("box_a", "box_b", "box_c", "puck")


@dataclass
class ContactLog:
    """Contacts between the robot and the table top seen since the last reset()."""
    arm_table: int = 0      # Panda link collision geoms touching the table / pedestal-free surfaces
    probe_table: int = 0    # probe geoms (tip, rod, paddle) touching the table top
    events: list = field(default_factory=list)

    def reset(self):
        self.arm_table = self.probe_table = 0
        self.events.clear()


class Sim:
    def __init__(self, xml=SCENE_XML):
        self.model = mujoco.MjModel.from_xml_path(str(xml))
        self.data = mujoco.MjData(self.model)
        m = self.model
        self.ctl = Controller(m, self.data)

        probe_body = m.body("probe").id
        self.probe_geoms = {g for g in range(m.ngeom) if m.geom_bodyid[g] == probe_body}
        arm_bodies = {m.body(f"link{i}").id for i in range(8)}
        self.arm_geoms = {g for g in range(m.ngeom) if m.geom_bodyid[g] in arm_bodies and m.geom_contype[g]}
        self.robot_geoms = self.probe_geoms | self.arm_geoms
        self.table_geom = m.geom("table_top").id
        self.puck_geom = m.geom("puck").id
        self.puck_body = m.body("puck").id
        self.goal_mocap = m.body_mocapid[m.body("goal").id]
        self.obj_qadr = {n: m.jnt_qposadr[m.body_jntadr[m.body(n).id]] for n in OBJECTS}
        self.obj_vadr = {n: m.jnt_dofadr[m.body_jntadr[m.body(n).id]] for n in OBJECTS}
        self._base_mass = float(m.body_mass[self.puck_body])
        self._base_inertia = m.body_inertia[self.puck_body].copy()
        self.friction_level = "normal"
        self.mass_level = "normal"
        self.contacts = ContactLog()
        self._force = np.zeros(6)
        self.reset()

    # ---- basic ---------------------------------------------------------------------------------
    @property
    def t(self) -> float:
        return float(self.data.time)

    def reset(self) -> None:
        mujoco.mj_resetData(self.model, self.data)
        self.ctl.reset()
        self.contacts.reset()

    def step(self) -> None:
        self.ctl.step()
        mujoco.mj_step(self.model, self.data)
        self._log_contacts()

    def settle(self, seconds: float = 0.5) -> None:
        for _ in range(int(seconds / self.model.opt.timestep)):
            self.step()

    # ---- contacts --------------------------------------------------------------------------------
    def _log_contacts(self) -> None:
        d = self.data
        for i in range(d.ncon):
            c = d.contact[i]
            g1, g2 = c.geom1, c.geom2
            if self.table_geom not in (g1, g2):
                continue
            other = g2 if g1 == self.table_geom else g1
            if other in self.arm_geoms:
                self.contacts.arm_table += 1
            elif other in self.probe_geoms:
                self.contacts.probe_table += 1

    def probe_contact(self, min_force: float = 0.3) -> tuple[float, float, float, float] | None:
        """If the probe presses on something non-robot with total normal force >= min_force,
        return (highest contact z, total normal force, x, y of that contact)."""
        d, m = self.data, self.model
        total, zmax, xy = 0.0, -np.inf, (0.0, 0.0)
        for i in range(d.ncon):
            c = d.contact[i]
            g1, g2 = c.geom1, c.geom2
            if (g1 in self.probe_geoms) == (g2 in self.probe_geoms):
                continue
            other = g2 if g1 in self.probe_geoms else g1
            if other in self.robot_geoms:
                continue
            mujoco.mj_contactForce(m, d, i, self._force)
            total += abs(self._force[0])
            if c.pos[2] > zmax:
                zmax, xy = c.pos[2], (c.pos[0], c.pos[1])
        return (float(zmax), total, float(xy[0]), float(xy[1])) if total >= min_force else None

    def touch(self) -> float:
        return float(self.data.sensor("tip_touch").data[0])

    # ---- ground truth --------------------------------------------------------------------------
    _RAY_GROUPS = np.array([1, 1, 0, 0, 0, 0], dtype=np.uint8)  # table (0) + objects (1); not robot

    def true_height(self, x: float, y: float) -> float:
        """Surface height at (x, y) by a ray straight down (robot geoms excluded)."""
        gid = np.zeros(1, dtype=np.int32)
        top = 1.0
        dist = mujoco.mj_ray(self.model, self.data, np.array([x, y, top]), np.array([0.0, 0.0, -1.0]),
                             self._RAY_GROUPS, 1, -1, gid)
        return top - dist if dist >= 0 else 0.0

    def true_height_grid(self, xs: Iterable[float], ys: Iterable[float]) -> np.ndarray:
        return np.array([[self.true_height(x, y) for x in xs] for y in ys])

    # ---- objects ---------------------------------------------------------------------------------
    def body_pos(self, name: str) -> np.ndarray:
        return self.data.xpos[self.model.body(name).id].copy()

    def puck_pose(self) -> tuple[np.ndarray, float]:
        """(xy, yaw) of the puck."""
        xmat = self.data.xmat[self.puck_body].reshape(3, 3)
        return self.data.xpos[self.puck_body][:2].copy(), float(np.arctan2(xmat[1, 0], xmat[0, 0]))

    def puck_tilt(self) -> float:
        """Angle (rad) between the puck axis and world z; > ~0.5 means it tipped over."""
        z = self.data.xmat[self.puck_body].reshape(3, 3)[:, 2]
        return float(np.arccos(np.clip(z[2], -1, 1)))

    def place(self, name: str, x: float, y: float, z: float | None = None, yaw: float = 0.0) -> None:
        qa, va = self.obj_qadr[name], self.obj_vadr[name]
        if z is None:
            z = self.data.qpos[qa + 2]
        self.data.qpos[qa:qa + 3] = (x, y, z)
        self.data.qpos[qa + 3:qa + 7] = (np.cos(yaw / 2), 0, 0, np.sin(yaw / 2))
        self.data.qvel[va:va + 6] = 0
        mujoco.mj_forward(self.model, self.data)

    def obj_speed(self, name: str) -> float:
        va = self.obj_vadr[name]
        return float(np.linalg.norm(self.data.qvel[va:va + 3]))

    def goal_xy(self) -> np.ndarray:
        return self.data.mocap_pos[self.goal_mocap][:2].copy()

    def set_goal_xy(self, x: float, y: float) -> None:
        self.data.mocap_pos[self.goal_mocap][:2] = (x, y)

    # ---- runtime physics changes ---------------------------------------------------------------
    def set_friction(self, level: str) -> None:
        """Sliding friction of the puck. The puck geom has priority=1 in scene.xml, so its own friction
        is used for all its contacts (table and paddle) instead of the max of the pair."""
        self.model.geom_friction[self.puck_geom, 0] = FRICTION_LEVELS[level]
        self.friction_level = level

    def set_mass(self, level: str) -> None:
        new = MASS_LEVELS[level]
        s = new / self._base_mass
        self.model.body_mass[self.puck_body] = new
        self.model.body_inertia[self.puck_body] = self._base_inertia * s
        mujoco.mj_setConst(self.model, self.data)
        self.mass_level = level

    def cycle_friction(self) -> str:
        keys = list(FRICTION_LEVELS)
        self.set_friction(keys[(keys.index(self.friction_level) + 1) % len(keys)])
        return self.friction_level

    def cycle_mass(self) -> str:
        keys = list(MASS_LEVELS)
        self.set_mass(keys[(keys.index(self.mass_level) + 1) % len(keys)])
        return self.mass_level


# ---- driving primitives ----------------------------------------------------------------------------
Task = Generator[None, None, object]


def run(sim: Sim, gen: Task, max_seconds: float = 60.0):
    """Drive a step-wise generator headlessly until it returns; return its value."""
    n = int(max_seconds / sim.model.opt.timestep)
    for _ in range(n):
        try:
            next(gen)
        except StopIteration as stop:
            return stop.value
        sim.step()
    raise TimeoutError(f"task did not finish in {max_seconds}s of sim time")


# GLFW key codes. Most letters are taken by the MuJoCo viewer's own shortcuts, so we use F-keys
# (on a Mac keyboard: fn + F-key). Change here if your keyboard needs something else.
KEY_F6, KEY_F7, KEY_F8, KEY_F9, KEY_F10 = 295, 296, 297, 298, 299
DEFAULT_KEYS = {
    KEY_F6: "auto",       # start / stop auto mode
    KEY_F7: "reset",
    KEY_F8: "truth",      # toggle ground-truth overlay
    KEY_F9: "friction",   # cycle low / normal / high
    KEY_F10: "mass",      # cycle light / normal / heavy
}


def run_viewer(
    sim: Sim,
    next_task: Callable[[Sim], Task | None],
    on_frame: Callable[[Sim, object], None] | None = None,
    on_key: Callable[[str, Sim], None] | None = None,
    keys: dict[int, str] = DEFAULT_KEYS,
    fps: float = 60.0,
) -> None:
    """Real-time passive viewer. `next_task(sim)` returns the next generator to run (or None to idle).
    `on_frame(sim, viewer)` runs once per rendered frame (e.g. to draw the overlay into viewer.user_scn)."""
    import mujoco.viewer

    state = {"auto": True, "pending": []}

    def key_cb(code: int) -> None:
        action = keys.get(code)
        if action:
            state["pending"].append(action)

    with mujoco.viewer.launch_passive(sim.model, sim.data, key_callback=key_cb) as viewer:
        task: Task | None = None
        frame_dt = 1.0 / fps
        steps_per_frame = max(1, round(frame_dt / sim.model.opt.timestep))
        while viewer.is_running():
            t0 = time.perf_counter()
            with viewer.lock():
                while state["pending"]:
                    action = state["pending"].pop(0)
                    if action == "auto":
                        state["auto"] = not state["auto"]
                    elif action == "reset":
                        sim.reset()
                        task = None
                    elif action == "friction":
                        print("friction:", sim.cycle_friction())
                    elif action == "mass":
                        print("puck mass:", sim.cycle_mass())
                    if on_key:
                        on_key(action, sim)
                for _ in range(steps_per_frame):
                    if task is None and state["auto"]:
                        task = next_task(sim)
                    if task is not None:
                        try:
                            next(task)
                        except StopIteration:
                            task = None
                    sim.step()
                if on_frame:
                    on_frame(sim, viewer)
            viewer.sync()
            time.sleep(max(0.0, frame_dt - (time.perf_counter() - t0)))
