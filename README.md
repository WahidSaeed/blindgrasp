# Blindgrasp

A blind Franka Panda arm in MuJoCo maps its table by touch, then pushes a puck to a goal around the
boxes it found. TabPFN is the only learner and never takes a gradient step: every probe and every push is
a new row in its context. See `Build Plan.md` for the full plan.

<p align="center"><img src="docs/media/mapping.gif" width="640" alt="The arm maps the table by touch; tiles are TabPFN's predicted heights"></p>

## The story

**Robots can't always see.** Dust, darkness or their own gripper block the camera. Blindgrasp asks what a robot can
do with touch alone: a Franka Panda in MuJoCo with no camera, whose only sense is a probe that touches the table and
reports a height.

**1. Map the table by touch.** Every touch becomes one row in TabPFN's context (`x, y, height`). TabPFN is a foundation
model for tables: it never trains, so the very next prediction already uses the new row. Its 10-90% band says where the
map is unsure, and the arm always touches the least certain spot next. Within a few dozen touches the boxes appear.

<p align="center"><img src="docs/media/map.png" width="720" alt="Touch map after 25 probes"></p>

**2. The world changes.** A presenter moves a box onto the puck's route. The map still says the route is clear; a map
is only as fresh as its last touch. So before every push the arm touches a few spots on the route, feels something
12 cm tall where the map said empty, re-touches an old spot to make sure it is a real change and not noise, drops the
stale rows and plans around the box.

<p align="center"><img src="docs/media/route_check.gif" width="640" alt="Route check: the probe finds the moved box"></p>

**3. Push the puck to the goal, in a few tries.** Pushing is learned the same way: each strike (direction, speed,
where the puck stopped) is one more row. Then the table turns icy. The first push overshoots, the prediction misses by
10 cm, the robot treats that as a physics change, drops its old pushes and is back on target two pushes later.

<p align="center"><img src="docs/media/icy_push.gif" width="640" alt="Icy table: overshoot, then back on target"></p>

**4. Watch it live in the browser.** A lab-workstation UI streams the simulation and lets you run the experiments,
move objects, change the table's friction and follow the map, the charts and the event log.

<p align="center"><img src="docs/media/ui.png" width="900" alt="Blindgrasp web UI with all panels open"></p>

## Evaluation

Measured with the scripts under `eval/` (3 seeds each; numbers and plots in `eval/out/`, copies in `docs/eval/`).

<p align="center"><img src="docs/eval/summary.png" width="900" alt="Height error: TabPFN 0.62 cm, kNN 0.62, GP 0.83. Median pushes: TabPFN 4 vs GP 5, after icy 2.5 vs 3"></p>

- **Mapping (80 touches):** TabPFN's height error (0.62 cm) beats the Gaussian process (0.83 cm) and ties nearest
  neighbours. Each touch is accurate to about 1 mm.
- **Pushing:** TabPFN reaches the goal in a median of 4 pushes from an empty context (GP 5), and 2.5 after the table
  turns icy (GP 3). All 9 + 6 goals were reached.
- **The limit:** box outlines (occupancy IoU) are no better than the GP's. With 80 touches every learner sits near the
  same ceiling: the number of touches, not the learner, is the limit.

| Map error and box outlines vs touches | After a box is moved (red line) |
|---|---|
| <img src="docs/eval/map_tabpfn_vs_baselines.png" alt="Map error and IoU vs probes for TabPFN, GP, kNN"> | <img src="docs/eval/map_recovery_tabpfn.png" alt="Recovery after a box is moved at probe 40"> |

| Change detection on the icy table | Is the uncertainty band honest? |
|---|---|
| <img src="docs/eval/push_icy_misses.png" alt="Prediction miss spikes when the table turns icy; resetting the context recovers in 2 pushes"> | <img src="docs/eval/calibration.png" alt="Share of outcomes below, inside and above the 10-90% band"> |

Resetting the push context on a detected change brings the prediction miss back down within 2 pushes; keeping the old
pushes takes 5-8. The 10-90% bands hold 73-83% of outcomes (ideal: 80%) for both learners, so "least certain" is a fair
guide for where to touch next.

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
`http://127.0.0.1:8000`); it reconnects on its own if the server restarts. If a static export of the UI exists
(`cd web && npm run build` -> `web/out`), the sim server also serves it at http://127.0.0.1:8000; otherwise it serves
the old single-file page there.

| `--mode`   | What it shows |
|------------|---------------|
| `map`      | Act 1: probe the most uncertain spot, map sharpens; move a box and it re-maps |
| `push`     | Act 2: few-shot pushing; make the table icy (F) and it re-adapts in a few pushes |
| `combined` | Acts 1 + 2: map, then push around the boxes the map found |
| `script`   | Presenter mode: the combined run with fixed seeds and scripted interrupts |

Learner: `--learner tabpfn|gp|knn|mlp` (also switchable in the page). For TabPFN on a laptop use the
slow-learner settings: `--n-estimators 1 --pred-step 0.04` (1-model ensemble, map predicted on a 4 cm grid
and upsampled). `--max-rows N` caps the context. `--speed` sets sim seconds per wall second.

The page is a dark lab-workstation layout: the live view in the middle, and three panels that start closed as
rails on the edges (Controls: experiments, interventions, parameters; Readouts: numbers, protocol, legend; Charts &
log). Open the ones you want; the choice is remembered. The top bar has the experiment picker, Run/Pause and Reset.
In the view: drag to orbit, Ctrl/⌘ + scroll (or the +/− buttons) to zoom, "Move an object" then click a box/puck/goal
and then the table to move it (Esc cancels). Interventions: table friction (normal / icy / sticky), puck mass,
ground-truth overlay.

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

Outputs go to `bench/out/` and `eval/out/` (tables, JSON, plots). `python -m eval.summary_chart` redraws the README chart;
`python -m eval.render_clips --mode script|map|push --clean --views front,hero` renders MP4s offline (deterministic per
seed; use `BLINDGRASP_BACKEND=local` to keep hosted TabPFN tokens).

## Layout

```
assets/        scene.xml (table, boxes, puck, goal), build_panda_probe.py -> panda_probe.xml
src/config.py  .env loading, backend/device choice, regressor factory (local or hosted)
src/sim/       env.py (scene, contacts, ground truth, friction/mass), controller.py (mink IK),
               primitives.py (probe_down, push as step-wise generators)
src/learn/     tabpfn_service.py (TabPFN, context tables, background fit thread), baselines.py (GP, kNN, MLP)
src/demos/     touch_map.py (Act 1), push.py (Act 2), combined.py (1 + 2), script.py (presenter mode)
src/viz/       overlay.py (map tiles, probe dots, push path)
src/web/       server.py (sim server: MJPEG /stream, /state, /action; serves web/out if built) + static/index.html
web/           Next.js UI (src/components/Dashboard.tsx, Viewport.tsx, LineChart.tsx; src/lib/sim.ts = API client)
bench/ eval/   latency benchmark, Phase 1 acceptance, map and push evaluations, render_clips.py (offline MP4s),
               summary_chart.py (docs/eval/summary.png)
docs/          README screenshots, GIFs and evaluation charts
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
- Mapping, 3 seeds x 80 probes (`eval/out/map_*.json`): TabPFN's height error (0.5-0.7 cm, mean 0.62) beats the GP
  (mean 0.83) and ties kNN (0.62), but it outlines boxes no better than GP (IoU 0.26-0.33 vs 0.37). Bigger ensembles, the full grid and the
  boundary-tracing strategy didn't change that much; neighbour features (`--learner tabpfn_nn`) help a little.
  Every learner sits near the ~0.37 ceiling for this many probes: probe count, not the learner, is the limit.
- Combined run: before each push the arm touches up to 3 unchecked spots on the puck's route (the map is only as
  fresh as its last touch: a box may have moved). Anything touched tall blocks paths straight away, whatever the
  learned map says. This is how the presenter-mode box move onto the route gets found and avoided.
- Puck mass doesn't matter for these pushes (< 0.6 cm change): the paddle is position-controlled and a sliding
  puck's stopping distance doesn't depend on mass. Use the icy table as the Act 2 interrupt.
- Pushing, 3 seeds (9 goals): TabPFN reaches goals in a median of 4 pushes from an empty context (GP 5), 2-3 after the
  table turns icy. The single-goal push demo (`--mode push`) has a longer first shot (~22 cm) and takes 6-7.
