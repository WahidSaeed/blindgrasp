import React from "react";
import { ACTS, cue, f, prog } from "../lib";
import { Clip, SEG, fit, speedLabel } from "../footage";
import { C, Chip, Frame } from "../theme";

const T = { start: f(ACTS.map[0]), amber: f(cue("Amber dots")), blue: f(cue("Blue is what")), mm: f(cue("Each touch is accurate")), boxes: f(cue("the boxes appear")), end: f(ACTS.map[1]) };

export const MapAct: React.FC<{ fr: number }> = ({ fr }) => {
  const s = fit(T.start, T.end, SEG.map0, SEG.map1);
  const p = prog(fr, T.start, 14);
  return (
    <>
      <div style={{ opacity: p, transform: `scale(${0.97 + 0.03 * p})` }}>
        <Frame label="Mapping by touch · TabPFN live" right={speedLabel(s.rate)} style={{ left: 60, top: 60, width: 1380, height: 900 }}>
          <Clip file="script2.mp4" {...s} />
        </Frame>
      </div>
      <div style={{ position: "absolute", left: 1480, top: 120, width: 400, display: "flex", flexDirection: "column", gap: 20 }}>
        {fr >= T.amber && <Chip fr={fr} at={T.amber} color={C.touch} big>dots = touches</Chip>}
        {fr >= T.blue && <Chip fr={fr} at={T.blue} color={C.model} big>tiles = TabPFN map</Chip>}
        {fr >= T.mm && <Chip fr={fr} at={T.mm} color={C.fg}>touch accuracy ≈ 1 mm</Chip>}
        {fr >= T.boxes && <Chip fr={fr} at={T.boxes} color={C.ok}>boxes found</Chip>}
      </div>
    </>
  );
};
