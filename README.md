# Blindgrasp

A blind Franka Panda arm in MuJoCo maps its table by touch, then pushes a puck to a goal around the
boxes it found. TabPFN is the only learner and never takes a gradient step: every probe and every push is
a new row in its context. See `Build Plan.md` for the full plan.

- **Live demo:** http://ec2-63-190-61-111.eu-central-1.compute.amazonaws.com (AWS EC2; one shared simulation, pauses when
  nobody watches; may be offline after the hackathon).
- **Pitch video (2:35):** `pitch/Blindgrasp_pitch_v1.mp4` (not in git; see [Pitch video](#pitch-video)).

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
(`cd web && npm run build` -> `web/out`), the sim server also serves it at http://127.0.0.1:8000 (same origin, as in the
Docker image); otherwise it serves the old single-file page there.

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
src/web/       server.py (sim server: MJPEG /stream, /state, /action; serves web/out if built) + static/index.html
web/           Next.js UI (src/components/Dashboard.tsx, Viewport.tsx, LineChart.tsx; src/lib/sim.ts = API client)
bench/ eval/   latency benchmark, Phase 1 acceptance, map and push evaluations, render_clips.py (offline MP4s)
deploy/aws/    EC2 boot scripts (user-data.sh, start.sh) and redeploy.sh
pitch/         pitch video: voiceover script, Remotion film (pitch/film), UI capture script
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
- Headless servers render in software (OSMesa): shadows cost ~2/3 of each frame, so they are off there
  (`RENDER_SHADOWS=1` turns them back on), and the simulation steps by elapsed wall time, so slow rendering lowers
  the frame rate but not the simulation speed.

## Deploy (AWS EC2, hosted TabPFN)

`deploy/aws/` runs everything as one container on an EC2 instance (Amazon Linux 2023, currently a c7i.xlarge in
eu-central-1; a t3.small ran the simulation 8x too slow). The `Dockerfile` builds the UI as a static export (`web/out`) and
a slim Python image (no PyTorch, no local weights, `BLINDGRASP_BACKEND=hosted`, headless MuJoCo via OSMesa, Menagerie Panda
pinned); the sim server serves the UI next to `/state`, `/action` and `/stream` on port 80 at the instance's default
address (`http://ec2-<ip>.<region>.compute.amazonaws.com`, plain HTTP, same origin).

- `user-data.sh` installs Docker and a `blindgrasp` boot service that runs `start.sh` (pull, build, run; adds 2 GB swap
  for the build). Video: `WIDTH=960 HEIGHT=600 FPS=15 SPEED=2` (about 10 fps in practice).
- The instance role reads `/blindgrasp/TABPFN_TOKEN` (SecureString) and `/blindgrasp/ALLOWED_ORIGINS` from SSM Parameter
  Store. Only port 80 is open; no SSH (use Session Manager).
- After pushing code or changing a parameter: run `deploy/aws/redeploy.sh` on your machine (restarts the service on the
  instance via SSM).
- One simulation is shared by everyone who opens the page, and so is the hosted TabPFN daily token cap (5M tokens,
  resets 00:00 UTC). When TabPFN fails the server switches to the GP. The simulation pauses when nobody is watching
  (`IDLE_AFTER`, default 60 s) to save CPU and tokens.
- Cost: the instance is billed per hour (c7i.xlarge about $0.20/h) plus the Elastic IP; stop or terminate it when done.

### Render + Vercel (not used)

`render.yaml` (Render free plan) and a Vercel UI (root `web/`, `NEXT_PUBLIC_SIM_URL` = the server URL, `ALLOWED_ORIGINS`
on the server = the Vercel URL) also work in principle, but the free plan's 512 MB limit kills the server (OSMesa pushes
it past 512 MB on Linux).

## Pitch video

`pitch/script.md` has the voiceover script (`pitch/vo_elevenlabs.txt`, generated with ElevenLabs), the shot plan and
where every number comes from. `pitch/film` is a Remotion project: each scene is timed from the voiceover's word
timestamps (`src/words.json`), with hand-split captions checked against the transcript.

```bash
# footage (local TabPFN; deterministic for a given seed). --views writes one MP4 per camera, --events a per-frame log
BLINDGRASP_BACKEND=local .venv/bin/python -m eval.render_clips --mode script --learner tabpfn --speed 3 --max-sim 200 \
    --width 1920 --height 1080 --clean --views front,hero,top --events pitch/footage/script2.json --out pitch/footage/script2.mp4
BLINDGRASP_BACKEND=local .venv/bin/python -m eval.render_clips --mode push --learner tabpfn --speed 3 \
    --width 1920 --height 1080 --clean --views hero,front --events pitch/footage/push.json --out pitch/footage/push.mp4
node pitch/ui_capture.mjs pitch/footage/ui        # screencast of the web UI (needs both servers running)
cd pitch/film && npm install && ./render.sh blindgrasp_pitch   # -> out/blindgrasp_pitch.mp4, -14 LUFS
```

The footage, voiceover and rendered video are not in git (`pitch/.gitignore`); link them into `pitch/film/public/`
before rendering. The TabPFN scene in the film is an illustration drawn in code (labelled as such); the robot shots are
real renders. Music is synthesized by `pitch/film/audio/music.py`.
