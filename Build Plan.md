
# Blindgrasp — Build Plan

*A blind robot arm that maps its world by touch and learns to push in-context. MuJoCo + TabPFN.*

As of 2026-11-21 · v2: adds TabPFN token setup and a hosted-API path

---

## 1. Goal and demo story

One MuJoCo scene, two acts: a blind Franka Panda arm maps its table by touch, then uses that map and a few test pushes to push a puck to a goal. TabPFN is the only learner, and it never runs a gradient step: every touch and push is a new row in its context.

### What the audience sees

1. **Act 1, map by touch.** The arm probes the table with a fingertip. A grid of tiles over the table shows the predicted height, faded where TabPFN is unsure. The arm always probes the most uncertain spot next, and the map sharpens in front of you.
2. **Interrupt.** A presenter drags a box to a new place with the mouse. The next probes contradict the map, the stale data is dropped, and the map corrects itself within a few touches.
3. **Act 2, few-shot pushing.** The arm pushes a puck toward a draggable goal marker. After a handful of pushes it predicts where the puck will go and hits the goal.
4. **Interrupt.** A key press makes the table icy or the puck heavy. The first push misses, the robot notices, and it re-adapts in a few pushes with no retraining.
5. **Side panel.** Live curves of map error vs number of touches and goal error vs number of pushes, TabPFN against a Gaussian process and a small MLP.

### Success criteria (proposed targets, checked in Phases 0 and 2)

| Area          | Target                                                                      |
| ------------- | --------------------------------------------------------------------------- |
| Map quality   | Height error under 1 cm and occupancy IoU of 0.8 or better within 40 probes |
| Map recovery  | Moved box is mapped again within 10 probes                                  |
| Pushing       | Puck within 3 cm of the goal within 10 pushes, from an empty context        |
| Adaptation    | Back under 3 cm within 5 pushes after a friction or mass change             |
| Interactivity | Viewer at 30 fps or more; a TabPFN map update in 1 s or less                |
| Evidence      | TabPFN beats the MLP baseline at 10 to 50 samples, averaged over 10 seeds   |

---

## 2. System architecture

The simulation never waits for TabPFN. The physics loop and the learner run on separate threads and share data through two stores: the context tables and the latest predictions.

```
┌──────────────────────── Main thread · every physics step ────────────────────────┐
│                                                                                  │
│  ┌─────────────────────┐    ┌─────────────────────┐    ┌──────────────────────┐  │
│  │ Task state machine  │───▶│ Primitives + mink IK│───▶│ MuJoCo scene + viewer│  │
│  │ MAP or PUSH mode    │    │ probe_down(), push()│    │ real-time physics    │  │
│  │ picks next action   │    │ one step per call   │    │ drag boxes and goal  │  │
│  │ draws map overlay   │    │                     │    │ keys: friction, mass │  │
│  └──────────▲──────────┘    └─────────────────────┘    └──────────┬───────────┘  │
└─────────────┼─────────────────────────────────────────────────────┼──────────────┘
              │ map + uncertainty, push model    new row per probe/push │
┌─────────────┼──────────── Worker thread · about once per second ────┼──────────────┐
│  ┌──────────┴──────────┐    ┌─────────────────────┐    ┌──────────▼───────────┐  │
│  │ Latest predictions  │◀───│ TabPFN regressors   │◀───│ Context tables       │  │
│  │ height map + uncert.│    │ refit on new rows   │    │ probes: x,y → height │  │
│  │ push outcome model  │    │ no gradient steps   │    │ pushes: push → dx,dy │  │
│  │ read without waiting│    │ median + 10/90% q.  │    │ stale rows pruned    │  │
│  └─────────────────────┘    └─────────────────────┘    └──────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

The main thread steps physics, runs the current primitive and redraws the overlay. The worker refits whenever new rows arrive and swaps in fresh predictions. The state machine always uses the latest predictions it has.

---

## 3. Tech stack and repo layout

Everything is plain Python running in one MuJoCo process. The only heavy dependency is TabPFN on a GPU.

| Piece              | Choice                                                            | Why                                                                                               |
| ------------------ | ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Simulator          | MuJoCo 3.x, `mujoco.viewer.launch_passive`                      | Our own control loop runs while the viewer stays interactive (drag bodies with Ctrl + right-drag) |
| Robot model        | Franka Panda from `mujoco_menagerie`                            | Well-tuned model with position actuators                                                          |
| Inverse kinematics | `mink` (differential IK for MuJoCo)                             | Cartesian targets to joint targets without writing a controller from scratch                      |
| Learner            | `tabpfn` (TabPFN-3.5), `TabPFNRegressor`                      | In-context regression with quantile output for uncertainty                                        |
| Learner, hosted    | `tabpfn-client`, authenticated with `TABPFN_TOKEN`            | Fallback when no fast GPU is available; same regressor interface                                  |
| Secrets            | `python-dotenv`, `.env` file (git-ignored)                    | The token is loaded from the environment and never committed                                      |
| Baselines          | scikit-learn `GaussianProcessRegressor`, small PyTorch MLP, kNN | The comparison that makes the in-context point                                                    |
| Live plots         | `rerun-sdk` (or matplotlib in a second window)                  | Curves next to the viewer without blocking the sim                                                |
| Video              | `mujoco.Renderer` offscreen + `imageio`                       | MP4 clips for slides and fallbacks                                                                |
| Hardware           | NVIDIA GPU with 8 GB or more                                      | TabPFN on CPU is likely too slow for a live map (see Phase 0)                                     |

```
blindgrasp/
  .env                        # TABPFN_TOKEN=...  (never committed)
  .env.example                # TABPFN_TOKEN=<your token>
  .gitignore                  # includes .env
  requirements.txt
  src/config.py               # loads .env, picks backend: local GPU or hosted
  assets/scene.xml            # table, boxes, puck, goal marker, includes the Panda
  src/sim/env.py              # load model, step loop, viewer, key callbacks
  src/sim/controller.py       # mink IK, Cartesian moves
  src/sim/primitives.py       # probe_down(), push(), as step-wise state machines
  src/learn/tabpfn_service.py # worker thread: context tables, fit, predict (local or hosted)
  src/learn/baselines.py      # GP, MLP, kNN with the same interface
  src/viz/overlay.py          # map tiles, probe dots, next-target marker in user_scn
  src/demos/touch_map.py      # Demo 1
  src/demos/push.py           # Demo 2
  src/demos/combined.py       # Acts 1 + 2 in one run
  bench/tabpfn_latency.py     # Phase 0 benchmark
  eval/                       # headless runs over seeds, plots
```

---

## 4. Phase 0: setup and latency benchmark (2 to 3 days)

This phase answers the question most likely to break the live demo: is TabPFN fast enough to update the map about once a second?

- [ ] Python 3.11 env; install `mujoco`, `mink`, `tabpfn`, `tabpfn-client`, `python-dotenv`, PyTorch with CUDA, `scikit-learn`, `rerun-sdk`, `imageio`
- [ ] Clone `mujoco_menagerie`; open the Panda scene in the viewer (on macOS the passive viewer has to be started with `mjpython`)
- [ ] Create `.env` with `TABPFN_TOKEN=...`, add `.env` to `.gitignore`, commit only `.env.example` with a placeholder
- [ ] `src/config.py`: load `.env`, read `TABPFN_TOKEN`, and choose the backend (`local` if a CUDA GPU is found, else `hosted`; overridable with `BLINDGRASP_BACKEND`)
- [ ] Check that the token works: one tiny fit + predict through `tabpfn-client`
- [ ] Download the TabPFN weights for local use; check whether that needs the same token or a license acceptance, and whether the license fits your use (research vs commercial)
- [ ] Write `bench/tabpfn_latency.py`: synthetic 2D height maps, context sizes 25 / 100 / 400 / 1,000 rows, query grids of 30 × 30 and 50 × 50 points
- [ ] Time fit + predict with quantiles for three backends: local GPU, local CPU, hosted API (include network round-trip; run 20 times and report the median and the slowest 5%)
- [ ] Check that the quantile spread actually tracks error on the synthetic maps (rough calibration)

**Decision gate.** Continue as planned if a 400-row context and a 30 × 30 grid predict in 1 s or less on some backend.

| Result                             | Backend for the live demo                                                       |
| ---------------------------------- | ------------------------------------------------------------------------------- |
| Local GPU at 1 s or less           | Local GPU; hosted API only as a fallback                                        |
| Only the hosted API at 1 s or less | Hosted API, plus a cached replay mode in case the venue network is bad          |
| Neither                            | Shrink the grid, cap the context with a sliding window, update every few probes |

**Done when:** the benchmark table is committed, the backend is chosen, and the grid size and update rate for Demo 1 are fixed.

---

## 5. Phase 1: scene and arm control (1 week)

This phase delivers two reliable motions, `probe_down` and `push`. Both run one step at a time, so the viewer never freezes.

### Scene (`assets/scene.xml`)

- Table 0.8 × 0.6 m in front of the Panda; 3 boxes of different sizes on free joints so they can be dragged
- Puck: a short cylinder on a free joint, with its own geom so friction and mass can be changed at runtime
- Goal: a mocap body with a flat disc, draggable in the viewer
- Fingertip: a small rigid probe rod in place of the gripper (or closed fingers), with a site and a `touch` sensor at its tip
- A flat paddle on the probe for pushing, so contacts are repeatable

### Control

- `controller.py`: mink IK from a Cartesian target to joint position targets, with a speed limit and a fixed downward tool orientation
- `probe_down(x, y)`: move to (x, y) at a safe height, descend slowly until the touch sensor passes a threshold or the table is reached, record the height, retract
- `push(angle, offset, distance, speed)`: place the paddle behind the puck at that angle with a sideways offset, push straight, retract; return the puck's displacement (dx, dy) and rotation
- Both written as generators that advance one physics step per call, driven by the main loop

### Interaction

- Key callbacks in the viewer: start/stop auto mode, reset, toggle ground-truth overlay, cycle friction (low / normal / high) and puck mass (light / normal / heavy)
- Friction via `model.geom_friction`, mass via `model.body_mass` with the inertia scaled to match

**Done when:** 100 random probes return heights within 3 mm of a ray cast at the same point, and 100 random pushes finish without the puck flipping or the arm hitting the table.

---

## 6. Phase 2: Demo 1, map by touch (1 to 1.5 weeks)

The map is a 2.5D height map: TabPFN predicts the table height at each (x, y), and the spread of its quantiles decides where to touch next.

### Learning problem

- Context row: `x, y → height` from each probe
- Prediction: median height plus the 10% and 90% quantiles on the display grid (size fixed in Phase 0)
- Uncertainty per cell = 90% minus 10% quantile; occupancy = predicted height above 1 cm
- Seed with 5 probes in a fixed spread pattern, then go active

### Choosing the next probe

- Score each grid cell by uncertainty minus a small travel-distance penalty; probe the best one
- Comparison modes: random probes and a fixed raster scan, for the evaluation curves

### Handling a moved box (the data goes stale)

- After each probe, compare the measurement with what the map predicted there before the probe
- An error over 2 cm means the world changed: drop the old probes within about 8 cm, and raise uncertainty there so the arm re-checks the area
- Optional: every 10th probe re-checks a random old point, so changes far from the arm are found too

### Overlay (`viz/overlay.py`)

- One thin tile per grid cell in `viewer.user_scn`; its height = predicted height, its colour = height, its transparency = uncertainty
- Probe dots: grey on the table, orange on an object; a ring marks the next target
- Ground truth: height map from `mj_ray` straight down at every cell, toggled with a key, also used for scoring

**Done when:** the map-quality and map-recovery targets are met in the live viewer, and the headless eval produces height-error and IoU curves for TabPFN, GP and MLP with both uncertainty-driven and random probing.

---

## 7. Phase 3: Demo 2, few-shot pushing (1 to 1.5 weeks)

TabPFN learns how each push moves the puck from the pushes made so far. A sampling planner then picks the push whose predicted result lands closest to the goal.

### Learning problem

- Context row: `push angle, sideways offset, push distance, speed → dx, dy` in the puck's frame (one regressor per target)
- Optional third target: puck rotation, to plan pushes that don't spin it
- Seed with 3 random pushes; every push after that is chosen by the planner and added to the context

### Planner

- Sample about 500 candidate pushes, predict each, score by distance from the predicted puck position to the goal
- Early on, either add the predicted spread to the score (cautious pushes) or subtract it (exploring pushes), and compare the two
- Replan after every push until the puck is within 3 cm of the goal; long distances take several pushes

### Handling a physics change

- If a push misses its prediction by more than twice the predicted spread, treat it as a change in the world
- Two modes, both shown: keep a sliding window of the last N pushes, or clear the context at a detected change and re-seed
- Also show a mode with no reset, where the robot keeps missing. The contrast makes the point about in-context learning.

**Done when:** the pushing and adaptation targets are met at every friction and mass setting, and the eval produces goal-error curves vs pushes for TabPFN, GP and MLP, before and after a change.

---

## 8. Phase 4: combined demo and evaluation (1 week)

The two demos connect through the map. Any push whose predicted puck path crosses an occupied cell is rejected, so the robot pushes around the boxes it found by touch.

### Combined run (`demos/combined.py`)

- State machine: MAP (until the map's mean uncertainty drops below a threshold) → PUSH → back to MAP if a push hits something unexpected
- Collision check: sample points along the line from puck to predicted end point against the occupancy map
- A scripted presenter mode with fixed seeds, so the live demo plays out the same way each time

### Evaluation (`eval/`, headless, 10 seeds each)

- Map: height error and IoU vs number of probes; uncertainty-driven vs random vs raster; TabPFN vs GP vs MLP vs kNN
- Map recovery: probes needed to re-map a moved box
- Push: goal error vs number of pushes; pushes needed to re-adapt after each friction and mass change
- Calibration: how often the true value falls inside TabPFN's 10 to 90% band (should be near 80%)
- Wall-clock cost per update for each learner

### Presentation assets

- 3 short MP4s (Act 1, Act 2, combined) rendered offscreen, as a fallback if the live demo fails
- One slide of curves per act; the headline is accuracy vs samples at 10 to 50 samples

**Done when:** the combined run works start to finish three times in a row live, and all plots and clips are exported.

---

## 9. Timeline, risks and mitigations

About 5 to 6 weeks for one developer working full time:

| Phase                             | Duration       |
| --------------------------------- | -------------- |
| 0 · Setup and latency benchmark  | 2 to 3 days    |
| 1 · Scene and arm control        | 1 week         |
| 2 · Demo 1, map by touch         | 1 to 1.5 weeks |
| 3 · Demo 2, few-shot pushing     | 1 to 1.5 weeks |
| 4 · Combined demo and evaluation | 1 week         |

Phases 2 and 3 share only the TabPFN service. Two people can build them in parallel and save about 1.5 weeks.

| Risk                                                  | Effect                                  | Mitigation                                                                                               |
| ----------------------------------------------------- | --------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| TabPFN too slow, especially on CPU                    | Map lags or freezes the demo            | Phase 0 gate across local GPU, CPU and hosted API; coarser grid, sliding window, update every few probes |
| Stale context after a box moves or friction changes   | Map or push model stays wrong           | Surprise check on every new row; drop nearby or old rows; periodic re-checks                             |
| Probe or paddle contact is jittery                    | Noisy heights, unrepeatable pushes      | Slow descent, threshold on touch sensor, flat paddle, small push distances                               |
| Puck spins or slides off the paddle                   | Displacement hard to predict            | Add rotation as a target, add sideways offset as a feature, limit push angle range                       |
| Uncertainty is miscalibrated                          | Arm probes the wrong places             | Calibration check in eval; fall back to the spread of a small ensemble                                   |
| IK hits joint limits or the table                     | Arm motions fail mid-demo               | Keep targets inside a tested workspace box; safe-height moves between primitives                         |
| Live demo fails on the day                            | Bad presentation                        | Scripted mode with fixed seeds; pre-rendered MP4s                                                        |
| TabPFN weight license                                 | Can't use it for the intended purpose   | Check the license terms in Phase 0, before building on it                                                |
| Token leaks (committed, pasted, shared)               | Someone else uses your quota or account | Keep it only in `.env`; rotate it if it has been shared anywhere                                       |
| Hosted API slow, rate-limited or offline at the venue | Map freezes during the live demo        | Local GPU first; record a cached replay of predictions; pre-rendered MP4s                                |
