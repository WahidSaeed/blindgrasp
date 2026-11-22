import React from "react";
import { AbsoluteFill, Audio, interpolate, staticFile, useCurrentFrame } from "remotion";
import { ACTS, ActName, Chunk, WORDS, chunk, clamp, f } from "./lib";
import { Finish } from "./kit/finish";
import { Bg, C, SANS } from "./theme";
import { Hook } from "./scenes/hook";
import { Intro } from "./scenes/intro";
import { Brain } from "./scenes/brain";
import { MapAct } from "./scenes/map";
import { Change } from "./scenes/change";
import { Push } from "./scenes/push";
import { Results } from "./scenes/results";
import { Outro } from "./scenes/outro";

const SCENES: Record<ActName, React.FC<{ fr: number }>> = { hook: Hook, intro: Intro, brain: Brain, map: MapAct, change: Change, push: Push, results: Results, outro: Outro };

// Captions: hand-split sense units, checked word-for-word against the transcript at load.
const LINES = [
  "Robots in the real world often can't see.", "Dust, darkness, or their own gripper blocks the camera.",
  "So what if a robot had to learn its table", "the way you find a light switch in the dark?", "By touch.",
  "This is Blindgrasp.", "A Franka Panda arm in a MuJoCo simulation", "with no camera at all.", "Its only sense is a probe.",
  "It touches the table and feels a height.", "Its job map the table,", "then push a puck to a goal, around whatever it found.",
  "The brain is TabPFN, a foundation model for tables,", "and it never trains, not a single gradient step.",
  "Every touch becomes one new row in its context.", "X, y, height.", "The very next prediction already knows about it.",
  "TabPFN also says how unsure it is,", "so the arm always touches where the map is least certain.",
  "Watch the map build.", "Amber dots are touches.", "Blue is what TabPFN predicts.", "Each touch is accurate to about a millimetre,",
  "and within a few dozen touches, the boxes appear.", "Now the world changes.", "Someone moves a box onto the puck's path.",
  "The map still says the route is clear", "because a map is only as fresh as its last touch.", "So before every push, the arm checks the route.",
  "It feels something tall where the map said empty.", "It retouches an old spot", "to confirm this is a real change, not noise.",
  "Then it drops the stale data and plans around the box.", "Pushing is learned the same way.",
  "Each strike, how hard, which direction,", "and where the puck stopped is just one more row.", "Starting from nothing,",
  "it reaches the goal in a median of four pushes.", "Then we make the table icy.", "The first push overshoots.",
  "The robot notices the surprise", "and is back on target in two or three pushes.",
  "We tested it against a Gaussian process", "and nearest neighbours over three seeds.", "TabPFN mapped heights more accurately",
  "than the Gaussian process,", "about six millimetres of error versus eight,", "and needed fewer pushes, four instead of five.",
  "And we measured the limit honestly.", "With eighty touches, box outlines are capped", "by how many points you touch, not by the learner.",
  "Blindgrasp runs live in your browser.", "Move a box, make the table icy,", "and watch it adapt in real time.",
  "A robot that learns from every single touch.", "Instantly.", "This is Blindgrasp.",
];
const CHUNKS: Chunk[] = chunk(WORDS, LINES);

const Captions: React.FC<{ fr: number }> = ({ fr }) => {
  const t = fr / 30;
  const c = CHUNKS.find((x) => t >= x.s - 0.05 && t < x.e);
  if (!c) return null;
  const o = Math.min(interpolate(fr, [f(c.s) - 2, f(c.s) + 3], [0, 1], clamp), interpolate(fr, [f(c.e) - 4, f(c.e)], [1, 0], clamp));
  return (
    <div style={{ position: "absolute", left: 0, right: 0, bottom: 44, display: "flex", justifyContent: "center", opacity: o }}>
      <div style={{ fontFamily: SANS, fontSize: 34, fontWeight: 500, color: C.fg, padding: "8px 20px", borderRadius: 10,
        background: "rgba(6,7,9,0.72)", textShadow: "0 2px 8px rgba(0,0,0,0.6)" }}>
        {c.words.map((w, i) => (
          <span key={i} style={{ opacity: t >= w.s - 0.02 ? 1 : 0.45 }}>{w.w}{i < c.words.length - 1 ? " " : ""}</span>
        ))}
      </div>
    </div>
  );
};

export const Film: React.FC<{ captions?: boolean }> = ({ captions = true }) => {
  const fr = useCurrentFrame();
  const t = fr / 30;
  const act = (Object.keys(ACTS) as ActName[]).find((k) => t >= ACTS[k][0] && t < ACTS[k][1]) ?? "outro";
  const S = SCENES[act];
  return (
    <AbsoluteFill style={{ background: C.bench }}>
      <Finish fr={fr} bloom={0.5}>
        <Bg />
        <S fr={fr} />
      </Finish>
      {captions && <Captions fr={fr} />}
      <Audio src={staticFile("vo.mp3")} />
      <Audio src={staticFile("music.wav")} volume={0.12} />
    </AbsoluteFill>
  );
};
