# Blindgrasp — 3-minute pitch video

Voiceover text to paste into ElevenLabs: `pitch/vo_elevenlabs.txt` (409 words, about 2:45–2:55).
"Tab P F N" and "Mu-Jo-Co" are spelled out so the voice says them right.

**ElevenLabs:** a calm, confident narrator voice, stability about 50%, similarity about 75%, speed 1.0. Export
one MP3 or WAV of the whole script (not per paragraph) and put it at `pitch/vo.mp3`. If it runs longer than
2:55, don't speed it up; tell me and I'll trim a sentence.

The cut is timed to your voice track: footage and animations follow the words, not the times below
(those are estimates).

| # | Approx. time | Voiceover (first words) | Visual | Type |
|---|---|---|---|---|
| 1 | 0:00–0:14 | "Robots in the real world often can't see…" | Dark screen; a camera icon fogs over and cuts out; a fingertip ripple pulses; the title "learn by touch" | Motion |
| 2 | 0:14–0:32 | "This is Blindgrasp…" | Logo reveal, then the arm in the sim: a slow orbit; "no camera" crossed-out eye badge; the probe tip highlighted with a callout "only sense: touch → height" | Footage + motion labels |
| 3 | 0:32–0:58 | "The brain is TabPFN…" | Animated table: each touch drops in as a row (x, y, height); the counter "gradient steps: 0" stays at 0; a blue heatmap updates with each row; an uncertainty glow points to the next touch | Motion |
| 4 | 0:58–1:15 | "Watch the map build…" | Live UI, sped up (labelled, e.g. "4× speed"): amber touches, blue prediction, boxes appear; the map-error chart falls | Footage (UI) |
| 5 | 1:15–1:50 | "Now, the world changes…" | Box moved onto the route (presenter beat), "map: clear ✓" callout turns into "felt: 6 cm ✗", re-touch ring, "CHANGE CONFIRMED" log line punched in, the new route drawn around the box | Footage + motion callouts |
| 6 | 1:50–2:20 | "Pushing is learned the same way…" | Puck strikes; a row-per-push table animates beside the footage; the error-to-goal per push shrinks; "ICY" frost wipe; overshoot; recovery in 2–3 | Footage + motion |
| 7 | 2:20–2:45 | "We tested it against…" | Animated bar charts: height error 0.6 vs 0.8 cm (TabPFN vs GP), median pushes 4 vs 5, after a change 2–3; an honest-limit note "outline accuracy is limited by number of touches" | Motion (data) |
| 8 | 2:45–3:00 | "Blindgrasp runs live in your browser…" | The workstation UI in a browser frame, panels opening; ending card: Blindgrasp, "a robot that learns from every touch", live URL and GitHub | Footage + motion |

Music: a subtle ambient or electronic bed, ducked under the voice, with a small swell on the logo and the end card.

## Numbers used (all measured in this repo)

- Probe accuracy within 1.1 mm (`eval.phase1_check`).
- Height error after 80 touches, 3 seeds (`eval/out/map_tabpfn_vs_baselines.json`): TabPFN 0.54–0.70 cm (mean
  0.62), GP 0.67–1.02 cm (mean 0.83). kNN was about the same as TabPFN (0.62), so the script compares against
  the GP only and doesn't claim "best of all".
- Pushes to reach the goal, 3 seeds (`eval/out/push_tabpfn_vs_gp.json`): TabPFN median 4 from an empty context
  vs GP 5; after the icy change TabPFN median 2.5 (2 with context reset, `push_icy.json`); 9/9 and 6/6 goals
  reached.
- Box-outline IoU is not a TabPFN win (all learners about 0.3–0.4 at 80 touches), so the script states the
  touch-count limit instead of claiming it.

## Video build (v1)

- Final: `pitch/Blindgrasp_pitch_v1.mp4` (1920x1080, 30 fps, 2:35, -14 LUFS).
- Remotion project: `pitch/film` (`./render.sh <name>`; scenes in `src/scenes/`, every cue timed from the voiceover words
  in `src/words.json`). Captions are hand-split lines checked word-for-word against the transcript.
- Footage: offline MuJoCo renders with `eval/render_clips.py --clean --views ... --events ...` (local TabPFN):
  `script2*` = guided demo to 200 s sim (map, box move, route check, change confirmed), `push*` = push demo seed 0
  (icy overshoot + recovery); `ui.mp4` = headless-Chrome screencast of the web UI (`pitch/ui_capture.mjs`).
- The TabPFN scene (map from rows) is an illustration drawn in code and labelled as such; all other robot shots are
  real renders. The push table shows that run's real pushes; "median 4 · 9 test goals" is from the evaluation.
- Music and accents are synthesized in `film/audio/music.py` (no samples, no licensing needed).
