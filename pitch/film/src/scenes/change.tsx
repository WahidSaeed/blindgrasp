import React from "react";
import { interpolate } from "remotion";
import { ACTS, clamp, cue, f, pop, prog } from "../lib";
import { Clip, SEG, fit, speedLabel } from "../footage";
import { C, Chip, Frame, MONO } from "../theme";

const T = {
  start: f(ACTS.change[0]), moves: f(cue("Someone moves a box")), still: f(cue("The map still says")), fresh: f(cue("only as fresh")),
  before: f(cue("So before every push")), feels: f(cue("It feels something tall")), retouch: f(cue("It retouches")), drops: f(cue("Then it drops")),
  around: f(cue("plans around the box")), end: f(ACTS.change[1]),
};
// Shots: the move (hero), the stale map (top), the route check and the change confirmed (hero), the new plan (top).
const SLOW = 0.5;   // the route check and the confirmation play slowly so they can be followed
const S3 = SEG.route - 7 - (T.feels - T.before) * SLOW;   // the tall touch lands on "It feels something tall"
const SHOTS = [
  { file: "script2_hero.mp4", ...fit(T.start, T.still, SEG.move - 25, SEG.move + 60) },
  { file: "script2.mp4", ...fit(T.still, T.before, SEG.move + 60, S3 - 40) },
  { file: "script2_hero.mp4", ...fit(T.before, T.drops, S3, S3 + (T.drops - T.before) * SLOW) },
  { file: "script2.mp4", ...fit(T.drops, T.end, S3 + (T.drops - T.before) * SLOW, SEG.end2) },
];

const Log: React.FC<{ fr: number; at: number; tag: string; color: string; text: string }> = ({ fr, at, tag, color, text }) => {
  const p = pop(fr, at);
  return (
    <div style={{ display: "flex", gap: 14, alignItems: "baseline", fontFamily: MONO, fontSize: 24, color: C.fg, opacity: interpolate(p, [0, 0.4], [0, 1], clamp), transform: `translateX(${(1 - p) * 20}px)` }}>
      <span style={{ color, fontWeight: 700, minWidth: 90 }}>{tag}</span><span>{text}</span>
    </div>
  );
};

export const Change: React.FC<{ fr: number }> = ({ fr }) => {
  const shot = SHOTS.find((s) => fr >= s.at && fr < s.at + s.dur) ?? SHOTS[SHOTS.length - 1];
  const flash = fr >= T.feels ? 1 - prog(fr, T.feels, 14) : 0;
  return (
    <>
      <Frame label="A box moves onto the route" right={speedLabel(shot.rate)} style={{ left: 60, top: 60, width: 1300, height: 820, borderColor: flash > 0 ? C.warn : undefined }}>
        {SHOTS.map((s, i) => <Clip key={i} file={s.file} at={s.at} dur={s.dur} src={s.src} rate={s.rate} />)}
        <div style={{ position: "absolute", inset: 0, boxShadow: `inset 0 0 120px rgba(255,90,82,${flash * 0.7})` }} />
      </Frame>
      {/* the map's belief vs what the probe felt */}
      <div style={{ position: "absolute", left: 1400, top: 90, width: 470, display: "flex", flexDirection: "column", gap: 18 }}>
        {fr >= T.moves && <Chip fr={fr} at={T.moves} color={C.warn} big>box moved</Chip>}
        {fr >= T.still && (
          <div style={{ padding: 24, borderRadius: 16, background: C.panel, border: `1.5px solid ${C.line2}`, opacity: prog(fr, T.still, 12) }}>
            <div style={{ fontFamily: MONO, fontSize: 20, color: C.fg3, letterSpacing: 2 }}>ON THE ROUTE</div>
            <div style={{ display: "flex", justifyContent: "space-between", fontFamily: MONO, fontSize: 30, marginTop: 14 }}>
              <span style={{ color: C.fg2 }}>map says</span><span style={{ color: C.model }}>clear</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontFamily: MONO, fontSize: 30, marginTop: 10, opacity: prog(fr, T.feels, 8) }}>
              <span style={{ color: C.fg2 }}>probe felt</span><span style={{ color: C.warn }}>tall ✗</span>
            </div>
            <div style={{ fontFamily: MONO, fontSize: 20, color: C.fg3, marginTop: 16, opacity: prog(fr, T.fresh, 12) }}>a map is only as fresh as its last touch</div>
          </div>
        )}
      </div>
      <div style={{ position: "absolute", left: 80, top: 905, display: "flex", flexDirection: "column", gap: 8 }}>
        {fr >= T.before && <Log fr={fr} at={T.before} tag="ROUTE" color={C.model} text="checking 3 spots on the puck's path" />}
        {fr >= T.retouch && <Log fr={fr} at={T.retouch} tag="VERIFY" color={C.touch} text="re-touching an old spot: real change, not noise" />}
      </div>
      <div style={{ position: "absolute", left: 1400, top: 520, width: 470, display: "flex", flexDirection: "column", gap: 16 }}>
        {fr >= T.retouch + 40 && <Chip fr={fr} at={T.retouch + 40} color={C.warn} big>CHANGE CONFIRMED</Chip>}
        {fr >= T.drops && <Chip fr={fr} at={T.drops} color={C.fg3}>stale rows dropped</Chip>}
        {fr >= T.around && <Chip fr={fr} at={T.around} color={C.ok} big>new route around it</Chip>}
      </div>
    </>
  );
};
