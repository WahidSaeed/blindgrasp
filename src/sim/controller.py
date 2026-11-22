"""Cartesian controller: mink differential IK -> Panda joint position targets.

IK runs on an arm-only model (assets/panda_probe.xml) so the scene's free bodies are not
decision variables. A setpoint moves toward the goal at a capped speed; IK tracks the setpoint
at `control_hz` and writes joint targets into data.ctrl.

Tool orientation is always "pointing down" with a yaw about world z:
    R(yaw) = Rz(yaw) @ Rx(pi)
Under R(yaw) the probe's local x axis maps to (cos yaw, sin yaw, 0) and the paddle normal
(local y) maps to (sin yaw, -cos yaw, 0).
"""
from __future__ import annotations

import mujoco
import mink
import numpy as np

from src.config import ROOT

IK_XML = ROOT / "assets" / "panda_probe.xml"
HOME_Q = np.array([0.0, 0.0, 0.0, -1.57079, 0.0, 1.57079, -0.7853])
ARM_JOINTS = [f"joint{i}" for i in range(1, 8)]


def wrap(a: float) -> float:
    return (a + np.pi) % (2 * np.pi) - np.pi


def tool_rotation(yaw: float) -> mink.SO3:
    return mink.SO3.from_z_radians(yaw) @ mink.SO3.from_x_radians(np.pi)


def yaw_from_xmat(xmat: np.ndarray) -> float:
    R = xmat.reshape(3, 3)
    return float(np.arctan2(R[1, 0], R[0, 0]))


class Controller:
    def __init__(
        self,
        model: mujoco.MjModel,
        data: mujoco.MjData,
        control_hz: float = 100.0,
        max_speed: float = 0.25,
        max_yaw_rate: float = 2.0,
    ):
        self.model, self.data = model, data
        self.ctrl_every = max(1, round(1.0 / (control_hz * model.opt.timestep)))
        self.ctrl_dt = self.ctrl_every * model.opt.timestep
        self.default_speed = max_speed
        self.max_yaw_rate = max_yaw_rate

        self.qadr = np.array([model.jnt_qposadr[model.joint(j).id] for j in ARM_JOINTS])
        self.tip_id = model.site("tip").id

        self.ik_model = mujoco.MjModel.from_xml_path(str(IK_XML))
        self.cfg = mink.Configuration(self.ik_model)
        self.task = mink.FrameTask("tip", "site", position_cost=1.0, orientation_cost=0.5, lm_damping=1e-3)
        self.posture = mink.PostureTask(self.ik_model, cost=1e-2)
        self.limits = [mink.ConfigurationLimit(self.ik_model)]
        self._tick = 0
        self.reset()

    # ---- state -------------------------------------------------------------------------------
    def reset(self, q: np.ndarray | None = None) -> None:
        q = HOME_Q if q is None else q
        self.data.qpos[self.qadr] = q
        self.data.qvel[self.qadr] = 0.0
        self.data.ctrl[:7] = q
        mujoco.mj_forward(self.model, self.data)
        self.cfg.update(q.copy())
        self.posture.set_target(HOME_Q)
        self.set_pos = self.tip_pos().copy()
        self.set_yaw = self.tip_yaw()
        self.goal_pos = self.set_pos.copy()
        self.goal_yaw = self.set_yaw
        self.speed = self.default_speed
        self._tick = 0

    def tip_pos(self) -> np.ndarray:
        return self.data.site_xpos[self.tip_id]

    def tip_yaw(self) -> float:
        return yaw_from_xmat(self.data.site_xmat[self.tip_id])

    def q(self) -> np.ndarray:
        return self.data.qpos[self.qadr]

    # ---- commands ----------------------------------------------------------------------------
    def set_goal(self, pos, yaw: float | None = None, speed: float | None = None, unwrapped: bool = False) -> None:
        """yaw: tool yaw about world z. By default the shortest rotation from the current setpoint is used;
        with unwrapped=True the value is used as-is (see paddle_yaw, which manages joint-7 range)."""
        self.goal_pos = np.asarray(pos, dtype=float).copy()
        if yaw is not None:
            self.goal_yaw = yaw if unwrapped else self.set_yaw + wrap(yaw - self.set_yaw)
        self.speed = speed or self.default_speed

    def paddle_yaw(self, push_angle: float, at_xy) -> float:
        """Unwrapped tool yaw putting the paddle normal along push_angle (either face) that keeps joint 7
        closest to the middle of its range once the tip is at at_xy.

        With the tool pointing down, joint 7 turns the tool about world z (tool yaw ~ -q7), and moving the
        tip to a new bearing turns joint 1, which adds to the tool yaw. So
            q7_new ~= q7_now - (yaw_new - yaw_now - d_bearing).
        """
        base = push_angle + np.pi / 2  # paddle normal = (sin yaw, -cos yaw) -> along u when yaw = angle + pi/2
        first = self.set_yaw + wrap(base - self.set_yaw)
        cands = first + np.pi * np.arange(-3, 4)
        bearing_now = np.arctan2(self.set_pos[1], self.set_pos[0])
        d_bearing = np.arctan2(at_xy[1], at_xy[0]) - bearing_now
        q7_now = float(self.cfg.q[6])
        q7_pred = q7_now - (cands - self.set_yaw - d_bearing)
        return float(cands[np.argmin(np.abs(q7_pred))])

    def hold(self) -> None:
        """Stop where the tip actually is (e.g. after contact)."""
        self.set_pos = self.tip_pos().copy()
        self.goal_pos = self.set_pos.copy()
        self.goal_yaw = self.set_yaw

    def setpoint_reached(self) -> bool:
        return bool(np.allclose(self.set_pos, self.goal_pos) and abs(self.set_yaw - self.goal_yaw) < 1e-6)

    def tracking_error(self) -> float:
        return float(np.linalg.norm(self.tip_pos() - self.set_pos))

    # ---- loop --------------------------------------------------------------------------------
    def step(self) -> None:
        """Call once per physics step, before mj_step."""
        self._tick += 1
        if self._tick % self.ctrl_every:
            return
        dt = self.ctrl_dt
        d = self.goal_pos - self.set_pos
        dist = np.linalg.norm(d)
        max_d = self.speed * dt
        self.set_pos = self.goal_pos.copy() if dist <= max_d else self.set_pos + d * (max_d / dist)
        dy = self.goal_yaw - self.set_yaw
        max_y = self.max_yaw_rate * dt
        self.set_yaw = self.goal_yaw if abs(dy) <= max_y else self.set_yaw + np.sign(dy) * max_y

        self.task.set_target(mink.SE3.from_rotation_and_translation(tool_rotation(self.set_yaw), self.set_pos))
        for _ in range(2):
            v = mink.solve_ik(self.cfg, [self.task, self.posture], dt, "daqp", damping=1e-3, limits=self.limits)
            self.cfg.integrate_inplace(v, dt / 2)
        self.data.ctrl[:7] = self.cfg.q[:7]
