# Blindgrasp

A blind Franka Panda arm in MuJoCo maps its table by touch, then pushes a puck to a goal around the
boxes it found. TabPFN is the only learner and never takes a gradient step: every probe and every push is
a new row in its context. See `Build Plan.md` for the full plan.

## Setup

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.txt
git clone --depth 1 --filter=blob:none --sparse https://github.com/google-deepmind/mujoco_menagerie.git
(cd mujoco_menagerie && git sparse-checkout set franka_emika_panda)
.venv/bin/python assets/build_panda_probe.py        # Panda + probe rod + push paddle -> assets/panda_probe.xml
cp .env.example .env                                # then put your Prior Labs key in .env (never in .env.example)
```

TabPFN needs `TABPFN_TOKEN` in `.env` for both paths:
- **local** weights (TabPFN 3.5, ~835 MB): accept the license once at
  `https://ux.priorlabs.ai/accept-license?hf_repo_id=tabpfn_3_5`; the weights download on first use.
- **hosted** API (`tabpfn-client`): metered, with a daily token cap that resets at 00:00 UTC.

`src/config.py` picks the backend: `BLINDGRASP_BACKEND=local|hosted` and `BLINDGRASP_DEVICE=cpu|mps|cuda`
override the default (local if a CUDA/MPS GPU exists, else hosted).

## Run the demo (browser)

Two processes: the Python sim server (physics, robot, TabPFN, video stream) and the Next.js UI.

```bash
.venv/bin/python -m src.web.server --mode script --learner tabpfn   # sim server on http://127.0.0.1:8000
cd web && npm install && npm run dev                                 # UI on http://localhost:3000
```

Open http://localhost:3000. The UI talks to the sim server at `NEXT_PUBLIC_SIM_URL` (default
`http://127.0.0.1:8000`); it reconnects on its own if the server restarts. The old single-file page is still
served at http://127.0.0.1:8000 as a fallback.

| `--mode`   | What it shows |
|------------|---------------|
| `map`      | Act 1: probe the most uncertain spot, map sharpens; move a box and it re-maps |
| `push`     | Act 2: few-shot pushing; make the table icy (F) and it re-adapts in a few pushes |
| `combined` | Acts 1 + 2: map, then push around the boxes the map found |
| `script`   | Presenter mode: the combined run with fixed seeds and scripted interrupts |

Learner: `--learner tabpfn|gp|knn|mlp` (also switchable in the page). For TabPFN on a laptop use the
slow-learner settings: `--n-estimators 1 --pred-step 0.04` (1-model ensemble, map predicted on a 4 cm grid
and upsampled). `--max-rows N` caps the context. `--speed` sets sim seconds per wall second.

In the page: drag to orbit, Ctrl/⌘ + scroll (or the +/− buttons) to zoom, click a box/puck/goal then the table
to move it. Keys: Space pause, R reset, T ground truth, F table friction (normal / icy / sticky), M puck mass,
1-4 switch act, ? shortcuts.

The native MuJoCo viewer also works (`.venv/bin/mjpython -m src.demos.touch_map`; F6-F10 keys), but the
browser viewer is the main one.

## Tests and evaluation

```bash
.venv/bin/python -m eval.phase1_check                           # 100 probes vs ray cast, 100 pushes (no flips / arm hits)
.venv/bin/python -m bench.tabpfn_latency --backends local:cpu hosted --n-estimators 1 8
.venv/bin/python -m eval.map_eval --learners tabpfn gp knn mlp --strategies active random raster --seeds 10
.venv/bin/python -m eval.map_eval --recovery                     # move the best-mapped box mid-run
.venv/bin/python -m eval.push_eval --learners tabpfn gp knn --adapt reset window none --seeds 10
```

Outputs go to `bench/out/` and `eval/out/` (tables, JSON, plots).

## Layout

```
assets/        scene.xml (table, boxes, puck, goal), build_panda_probe.py -> panda_probe.xml
src/config.py  .env loading, backend/device choice, regressor factory (local or hosted)
src/sim/       env.py (scene, contacts, ground truth, friction/mass), controller.py (mink IK),
               primitives.py (probe_down, push as step-wise generators)
src/learn/     tabpfn_service.py (TabPFN, context tables, background fit thread), baselines.py (GP, kNN, MLP)
src/demos/     touch_map.py (Act 1), push.py (Act 2), combined.py (1 + 2), script.py (presenter mode)
src/viz/       overlay.py (map tiles, probe dots, push path)
src/web/       server.py (sim server: MJPEG /stream, /state, /action) + static/index.html (fallback page)
web/           Next.js UI (src/components/Dashboard.tsx, Viewport.tsx, LineChart.tsx; src/lib/sim.ts = API client)
bench/ eval/   latency benchmark, Phase 1 acceptance, map and push evaluations
```

## Findings so far (see the build plan for targets)

- Reach: the arm can't reach the plan's far table edge; probes/pushes use a tested workspace
  (box x 0.20-0.72 m, |y| <= 0.35 m, 0.32-0.80 m from the base).
- Probe accuracy: within 1.1 mm of the surface; edge contacts are reported at the contact point.
- The 6 mm tip footprint dilates every box by ~6 mm; even probing every cell caps geometric IoU near 0.78,
  so map IoU is scored against what a probe would feel ("touch truth"), with geometric IoU reported too.
- Pushes are strikes (paddle speed at contact + follow-through): slow position-controlled pushes made the
  puck's travel independent of friction and mass, leaving nothing to learn and no change to detect.
- A probe that contradicts the map is verified by re-touching an old spot before any data is dropped.
- TabPFN backend (`bench/out/latency.md`): local CPU, 1-model ensemble, coarse grid = 0.4-0.75 s per update.
  Apple GPU and the hosted API (~2.6 s/call) are slower on this laptop.
- Mapping, 3 seeds x 80 probes (`eval/out/map_*.json`): TabPFN has the lowest height error (0.5-0.6 cm vs GP 0.8)
  but outlines boxes no better than GP (IoU 0.26-0.33 vs 0.37). Bigger ensembles, the full grid and the
  boundary-tracing strategy didn't change that much; neighbour features (`--learner tabpfn_nn`) help a little.
  Every learner sits near the ~0.37 ceiling for this many probes: probe count, not the learner, is the limit.
- Combined run: before each push the arm touches up to 3 unchecked spots on the puck's route (the map is only as
  fresh as its last touch: a box may have moved). Anything touched tall blocks paths straight away, whatever the
  learned map says. This is how the presenter-mode box move onto the route gets found and avoided.
- Puck mass doesn't matter for these pushes (< 0.6 cm change): the paddle is position-controlled and a sliding
  puck's stopping distance doesn't depend on mass. Use the icy table as the Act 2 interrupt.
- Pushing, 3 seeds: TabPFN reaches goals in a median of 4 pushes from an empty context (GP 5), 3 after a change.

## Deploy (Render + Vercel, hosted TabPFN)

- **Sim server → Render.** `Dockerfile` builds a slim image (no PyTorch, no local weights; `BLINDGRASP_BACKEND=hosted`,
  headless MuJoCo via OSMesa). `render.yaml` is a Blueprint for it (free plan; video defaults to 640x400 @ 8 fps - raise `WIDTH`/`HEIGHT`/`FPS` on a paid plan). Set two env vars in
  the Render dashboard: `TABPFN_TOKEN` (secret) and `ALLOWED_ORIGINS` (the Vercel URL, e.g. `https://blindgrasp.vercel.app`).
- **UI → Vercel.** Import the repo with root directory `web/` and set `NEXT_PUBLIC_SIM_URL` to the Render URL
  (e.g. `https://blindgrasp-sim.onrender.com`). Redeploy after changing it - it is baked in at build time.
- One simulation is shared by everyone who opens the page, and the hosted TabPFN daily token cap is shared too.

### AWS (EC2) instead of Render

`deploy/aws/` runs the sim server and the UI (`web/Dockerfile`, Next.js standalone) on one EC2 t3.small (Amazon Linux 2023)
with Caddy in front for automatic HTTPS on `<elastic-ip-with-dashes>.sslip.io`: `/state`, `/action`, `/stream` go to the
sim server, everything else to the UI (same origin, so the UI needs no `NEXT_PUBLIC_SIM_URL`). The simulation pauses when
nobody is watching (`IDLE_AFTER`, default 60 s) to save CPU and TabPFN tokens. `user-data.sh` installs Docker and a `blindgrasp` boot service that runs `start.sh`
(pull, build, run). The instance role reads `/blindgrasp/TABPFN_TOKEN` (SecureString) and `/blindgrasp/ALLOWED_ORIGINS`
from SSM Parameter Store; no SSH, use Session Manager. Restart the service after changing a parameter:
`sudo systemctl restart blindgrasp`.

