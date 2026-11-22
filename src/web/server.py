"""Browser front-end: the simulation and learner run here in Python; the page shows an MJPEG stream,
controls and live curves. No mjpython or GLFW window needed.

    .venv/bin/python -m src.web.server                 # then open http://127.0.0.1:8000
    .venv/bin/python -m src.web.server --learner tabpfn --speed 2

Mouse on the video: drag = orbit, wheel = zoom, click a box/puck/goal to select it, then click the
table to move it there (this is the "presenter moves a box" interrupt).

Binds to 127.0.0.1 by default (HOST/PORT env vars or --host/--port override). There is no auth: anyone who can reach
it can drive the shared simulation. In production set ALLOWED_ORIGINS to the UI's URL.
"""
from __future__ import annotations

import argparse
import io
import os
import json
import queue
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import mujoco
import numpy as np
from PIL import Image

from src.demos.combined import combined_task
from src.demos.script import SEED as SCRIPT_SEED
from src.demos.script import scripted_task
from src.demos.push import PushAgent, pushing_task
from src.demos.touch_map import DROP_RADIUS, TouchMap, mapping_task
from src.learn.baselines import learner_kwargs
from src.sim.env import Sim
from src.viz.overlay import Overlay

STATIC = Path(__file__).resolve().parent / "static"
SELECTABLE = ("box_a", "box_b", "box_c", "puck", "goal")
HALF_HEIGHT = {"box_a": 0.04, "box_b": 0.03, "box_c": 0.06, "puck": 0.02}


class App:
    """Owns the sim, the learner, the renderer and the camera. Everything runs on one thread (run())."""

    def __init__(self, learner: str, strategy: str, width: int, height: int, fps: float, speed: float,
                 mode: str = "map", adapt: str = "reset", n_estimators: int | None = None,
                 pred_step: float | None = None, max_rows: int | None = None):
        self.n_estimators, self.pred_step, self.max_rows = n_estimators, pred_step, max_rows
        self.learner, self.strategy, self.mode, self.adapt = learner, strategy, mode, adapt
        self.agent: PushAgent | None = None
        self.width, self.height, self.fps, self.speed = width, height, fps, speed
        self.actions: queue.Queue = queue.Queue()
        self.frame_cv = threading.Condition()
        self.jpeg: bytes | None = None
        self.frame_id = 0
        self.allowed_origins: set[str] = {"*"}
        # Idle when nobody is watching: no open video stream and no /state poll for IDLE_AFTER seconds.
        # Saves CPU and hosted TabPFN tokens on a shared server; the run resumes where it left off.
        self.viewers = 0
        self.viewer_lock = threading.Lock()
        self.last_seen = time.monotonic()
        self.idle_after = float(os.environ.get("IDLE_AFTER", "60"))
        self.idle = False
        self.state_lock = threading.Lock()
        self.state: dict = {}
        self.stop = threading.Event()
        self.error: str | None = None

    # ---- setup -------------------------------------------------------------------------------------
    def _new_run(self) -> None:
        if getattr(self, "tm", None) is not None:
            self.tm.service.shutdown()
        if self.agent is not None:
            self.agent.shutdown()
            self.agent = None
        self.sim.reset()
        # TabPFN picked in the page: use the live-demo settings from bench/out/latency.md unless overridden on
        # the command line (1-model ensemble; plain TabPFN predicts on a 4 cm grid, the neighbour-feature variant
        # needs the full grid).
        tab = self.learner.startswith("tabpfn")
        lk = learner_kwargs(self.learner, self.n_estimators or (1 if tab else None))
        pred_step = self.pred_step or (0.04 if self.learner == "tabpfn" else None)
        seed = SCRIPT_SEED if self.mode == "script" else 0
        self.tm = TouchMap(self.learner, self.strategy, seed=seed, learner_kwargs=lk, pred_step=pred_step,
                           max_rows=self.max_rows)
        self.ov = Overlay(self.tm.xs, self.tm.ys)
        self.ui = {"probes": [], "next": None, "plan": None, "pushes": [], "log": [], "status": ""}
        self.task = None
        self.curve: list[dict] = []
        if self.mode == "push":
            # Act 2 on its own: park the boxes where the arm can't reach (in front of the base / table edge).
            self.sim.place("box_a", 0.20, 0.15, 0.04)
            self.sim.place("box_c", 0.20, -0.15, 0.06)
            self.sim.place("box_b", 0.68, 0.37, 0.03)
            self.sim.place("puck", 0.42, -0.05, 0.02)
            self.sim.set_goal_xy(0.60, 0.10)
            self.agent = PushAgent(self.learner, self.adapt, learner_kwargs=lk)
        elif self.mode == "script":
            self.sim.set_friction("normal")
            self.sim.set_mass("normal")
            self.agent = PushAgent(self.learner, self.adapt, seed=SCRIPT_SEED, learner_kwargs=lk)
        elif self.mode == "combined":
            self.sim.place("puck", 0.45, 0.0, 0.02)
            self.sim.set_goal_xy(0.66, 0.05)
            self.agent = PushAgent(self.learner, self.adapt, learner_kwargs=lk)
        what = {"push": f"pushing, adapt={self.adapt}", "map": f"mapping, probing={self.strategy}",
                "combined": "map then push around the boxes", "script": "presenter script"}[self.mode]
        self.events: list[str] = [f"new run: {what}, learner={self.learner}"]
        self.seen_version = -1
        self.truth = None
        self.selected: str | None = None

    def _log(self, msg: str) -> None:
        self.events.append(f"[{self.sim.t:6.1f}s] {msg}")
        self.events = self.events[-40:]

    # ---- actions from the browser -----------------------------------------------------------------
    def _apply(self, a: dict) -> None:
        name = a.get("name")
        if name == "auto":
            self.auto = not self.auto
        elif name == "reset":
            self._new_run()
        elif name == "truth":
            self.show_truth = not self.show_truth
        elif name == "friction":
            self._log(f"puck friction -> {self.sim.cycle_friction()}")
        elif name == "mass":
            self._log(f"puck mass -> {self.sim.cycle_mass()}")
        elif name == "speed":
            self.speed = float(np.clip(a.get("value", 1), 0.25, 8))
        elif name == "learner":
            self.learner = a.get("value", self.learner)
            self._new_run()
        elif name == "strategy":
            self.strategy = a.get("value", self.strategy)
            self._new_run()
        elif name == "mode":
            self.mode = a.get("value", self.mode)
            self._new_run()
        elif name == "adapt":
            self.adapt = a.get("value", self.adapt)
            if self.agent is not None:
                self.agent.adapt = self.adapt
                self._log(f"adaptation mode -> {self.adapt}")
        elif name == "orbit":
            self.cam.azimuth -= float(a.get("dx", 0)) * 0.3
            self.cam.elevation = float(np.clip(self.cam.elevation - float(a.get("dy", 0)) * 0.3, -89, -5))
        elif name == "zoom":
            self.cam.distance = float(np.clip(self.cam.distance * (1.0015 ** float(a.get("delta", 0))), 0.5, 4))
        elif name == "view":
            self._set_view(a.get("value", "front"))
        elif name == "click":
            self._click(float(a["x"]), float(a["y"]))

    def _set_view(self, v: str) -> None:
        c = self.cam
        c.lookat[:] = (0.45, 0.0, 0.02)
        c.distance, c.azimuth, c.elevation = {"front": (1.35, 180, -40), "top": (1.25, 180, -89),
                                              "side": (1.4, 240, -30)}.get(v, (1.35, 180, -40))

    def _click(self, relx: float, rely: float) -> None:
        """relx, rely in [0, 1] from the image's top-left."""
        selpnt = np.zeros(3)
        geomid, flexid, skinid = np.array([-1], np.int32), np.array([-1], np.int32), np.array([-1], np.int32)
        mujoco.mjv_select(self.sim.model, self.sim.data, self.vopt, self.width / self.height, relx, 1 - rely,
                          self.renderer.scene, selpnt, geomid, flexid, skinid)
        g = int(geomid[0])
        if g < 0:
            return
        body = self.sim.model.body(self.sim.model.geom_bodyid[g]).name
        if body in SELECTABLE:
            self.selected = None if self.selected == body else body
            if self.selected:
                self._log(f"selected {body} - click the table to move it")
            return
        if self.selected and selpnt[2] < 0.15 and body in ("table", "world", ""):
            x, y = float(selpnt[0]), float(selpnt[1])
            if self.selected == "goal":
                self.sim.set_goal_xy(x, y)
            else:
                self.sim.place(self.selected, x, y, HALF_HEIGHT[self.selected] + 0.002, 0.0)
            self._log(f"moved {self.selected} to ({x:.2f}, {y:.2f})")
            self.selected = None

    # ---- main loop ---------------------------------------------------------------------------------
    def run(self) -> None:
        try:
            self._run()
        except Exception as e:  # noqa: BLE001 - surface errors in the page instead of dying silently
            import traceback

            self.error = traceback.format_exc()
            print(self.error)
            raise

    def _run(self) -> None:
        self.sim = Sim()
        self.renderer = mujoco.Renderer(self.sim.model, self.height, self.width, max_geom=10000)
        self.vopt = mujoco.MjvOption()
        self.cam = mujoco.MjvCamera()
        self._set_view("front")
        self.auto, self.show_truth = True, False
        self.tm = None
        self._new_run()
        dt = self.sim.model.opt.timestep
        frame_dt = 1.0 / self.fps
        last_metric_t = 0.0
        while not self.stop.is_set():
            t0 = time.perf_counter()
            idle = self.viewers == 0 and time.monotonic() - self.last_seen > self.idle_after
            if idle != self.idle:
                self.idle = idle
                print("idle: nobody watching, simulation paused" if idle else "viewer connected, simulation resumed", flush=True)
            if idle:
                time.sleep(0.25)
                continue
            while not self.actions.empty():
                self._apply(self.actions.get())

            n_steps = max(1, round(self.speed * frame_dt / dt))
            for _ in range(n_steps):
                if self.auto and self.task is None:
                    self.task = {"push": lambda: pushing_task(self.sim, self.agent, self.ui),
                                 "map": lambda: mapping_task(self.sim, self.tm, self.ui),
                                 "combined": lambda: combined_task(self.sim, self.tm, self.agent, self.ui),
                                 "script": lambda: scripted_task(self.sim, self.tm, self.agent, self.ui)}[self.mode]()
                if self.auto and self.task is not None:
                    next(self.task)
                self.sim.step()
            futs = [self.tm.service.pending] + ([self.agent.svc_along.pending] if self.agent else [])
            fut = next((f for f in futs if f is not None and f.done() and f.exception() is not None), None)
            if fut is not None:
                err = fut.exception()
                msg = str(err).strip().splitlines()[0] if str(err).strip() else type(err).__name__
                self.learner = "gp" if self.learner != "gp" else "knn"
                self._new_run()
                self._log(f"learner failed ({type(err).__name__}: {msg[:160]}); switched to {self.learner}")
            while self.ui["log"]:
                self._log(self.ui["log"].pop(0))
            if self.mode != "push":
                self.tm.update()
                self._track_events()

            p = self.tm.service.latest
            if self.mode != "push" and p is not None and p.version != self.seen_version:
                self.seen_version = p.version
                self.truth = self.tm.truth_grid(self.sim)
                m = self.tm.metrics(self.truth)
                self.curve.append({"n": self.tm.n, "mae_cm": m["mae"] * 100, "iou": m["iou"],
                                   "band_cm": m["band"] * 100, "fit_s": p.seconds})
            elif self.show_truth and time.perf_counter() - last_metric_t > 1.0:
                self.truth = self.tm.truth_grid(self.sim)
                last_metric_t = time.perf_counter()

            if self.viewers > 0 or self.jpeg is None:
                self._render()
            self._publish_state()
            time.sleep(max(0.0, frame_dt - (time.perf_counter() - t0)))

    def _track_events(self) -> None:
        evs = self.tm.events
        k = getattr(self, "_ev_seen", 0)
        if len(evs) < k:
            k = 0
        for ev in evs[k:]:
            if ev.confirmed:
                self._log(f"probe {ev.n + 1}: CHANGE CONFIRMED - a spot touched before now reads "
                          f"{ev.height*100:.1f} cm; dropped {ev.dropped} stale rows within {DROP_RADIUS*100:.0f} cm")
            elif ev.surprise and ev.verify:
                self._log(f"probe {ev.n + 1}: surprise - felt {ev.height*100:.1f} cm, map said "
                          f"{ev.predicted*100:.1f} cm; re-checking an old point nearby")
        self._ev_seen = len(evs)

    def _render(self) -> None:
        r = self.renderer
        r.update_scene(self.sim.data, camera=self.cam, scene_option=self.vopt)
        if self.mode in ("push", "combined", "script"):
            path, ok = None, True
            if self.ui.get("plan") is not None:
                start, end, rnd = self.ui["plan"]
                path = [tuple(start), tuple(end)] if end is not None else None
                ok = not rnd
            self.ov.draw(r.scene, path=path, path_ok=ok, clear=False)
        pr = self.tm.prediction() if self.mode != "push" else None
        if self.mode != "push":
            self.ov.draw(r.scene,
                     height=None if pr is None else pr[1], band=None if pr is None else pr[2] - pr[0],
                     probes=self.ui["probes"], next_target=self.ui["next"],
                     truth=self.truth if self.show_truth else None, mask=self.tm.mask, clear=False)
        if self.selected:
            pos = self.sim.body_pos(self.selected)
            g = r.scene.geoms[r.scene.ngeom] if r.scene.ngeom < r.scene.maxgeom else None
            if g is not None:
                mujoco.mjv_initGeom(g, mujoco.mjtGeom.mjGEOM_SPHERE, np.array([0.012, 0, 0]),
                                    pos + np.array([0, 0, 0.1]), np.eye(3).ravel(), np.array([1, 1, 0, 1], np.float32))
                r.scene.ngeom += 1
        img = r.render()
        buf = io.BytesIO()
        Image.fromarray(img).save(buf, "JPEG", quality=80)
        with self.frame_cv:
            self.jpeg = buf.getvalue()
            self.frame_id += 1
            self.frame_cv.notify_all()

    def _publish_state(self) -> None:
        p = self.tm.service.latest
        with self.state_lock:
            self.state = {
                "t": self.sim.t, "auto": self.auto, "speed": self.speed, "learner": self.learner,
                "strategy": self.strategy, "probes": self.tm.n, "rows": len(self.tm.table),
                "fitting": self.tm.service.busy(), "fit_s": None if p is None else p.seconds,
                "friction": self.sim.friction_level, "mass": self.sim.mass_level, "truth": self.show_truth,
                "selected": self.selected, "curve": self.curve[-300:], "events": self.events[-15:],
                "mode": self.mode, "adapt": self.adapt, "pushes": self.ui["pushes"][-200:],
                "push_status": self.ui.get("status", ""), "phase": self.ui.get("phase"), "beat": self.ui.get("beat"),
                "push_rows": len(self.agent.X) if self.agent else 0,
                "error": self.error,
            }

    def snapshot(self) -> dict:
        with self.state_lock:
            return dict(self.state)


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep the terminal quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self._cors()
            self.end_headers()
            self.wfile.write(body)

        def _cors(self) -> None:
            # The Next.js UI calls this server from another origin (localhost:3000 locally, Vercel in production).
            origin = self.headers.get("Origin", "")
            allowed = app.allowed_origins
            if "*" in allowed:
                self.send_header("Access-Control-Allow-Origin", "*")
            elif origin in allowed:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def do_OPTIONS(self):
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            elif self.path == "/state":
                app.last_seen = time.monotonic()
                self._send(200, json.dumps(app.snapshot()).encode(), "application/json")
            elif self.path.startswith("/stream"):
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-store")
                self._cors()
                self.end_headers()
                last = -1
                with app.viewer_lock:
                    app.viewers += 1
                app.last_seen = time.monotonic()
                try:
                    while not app.stop.is_set():
                        with app.frame_cv:
                            app.frame_cv.wait_for(lambda: app.frame_id != last or app.stop.is_set(), timeout=1.0)
                            jpg, last = app.jpeg, app.frame_id
                        if jpg is None:
                            continue
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                         + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    with app.viewer_lock:
                        app.viewers -= 1
                    app.last_seen = time.monotonic()
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self):
            if self.path != "/action":
                return self._send(404, b"not found", "text/plain")
            app.last_seen = time.monotonic()
            n = int(self.headers.get("Content-Length", 0))
            try:
                a = json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError:
                return self._send(HTTPStatus.BAD_REQUEST, b"bad json", "text/plain")
            app.actions.put(a)
            self._send(200, b"{}", "application/json")

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--learner", default="gp", choices=["tabpfn", "tabpfn_nn", "gp", "knn", "mlp"])
    ap.add_argument("--strategy", default="active", choices=["active", "lse", "random", "raster"])
    ap.add_argument("--mode", default="map", choices=["map", "push", "combined", "script"])
    ap.add_argument("--adapt", default="reset", choices=["reset", "window", "none"])
    ap.add_argument("--n-estimators", type=int, default=None, help="TabPFN ensemble size (fewer = faster)")
    ap.add_argument("--pred-step", type=float, default=None, help="predict the map on a coarser grid (m), e.g. 0.04")
    ap.add_argument("--max-rows", type=int, default=None, help="cap the map context to the most recent N rows")
    # Hosting platforms (Render etc.) pass HOST/PORT in the environment.
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    ap.add_argument("--width", type=int, default=960)
    ap.add_argument("--height", type=int, default=600)
    ap.add_argument("--fps", type=float, default=25)
    ap.add_argument("--speed", type=float, default=2.0, help="sim seconds per wall second")
    args = ap.parse_args()

    app = App(args.learner, args.strategy, args.width, args.height, args.fps, args.speed, args.mode, args.adapt,
              args.n_estimators, args.pred_step, args.max_rows)
    # Which web origins may call this server (comma-separated). "*" is fine locally; set it to the UI's URL in production.
    app.allowed_origins = {o.strip().rstrip("/") for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()}
    sim_thread = threading.Thread(target=app.run, name="sim", daemon=True)
    sim_thread.start()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(app))
    server.daemon_threads = True
    print(f"Blindgrasp web viewer on http://{args.host}:{args.port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.stop.set()
        server.shutdown()


if __name__ == "__main__":
    main()
