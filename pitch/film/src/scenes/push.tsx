import React from "react";
import { interpolate } from "remotion";
import { ACTS, clamp, cue, f, prog } from "../lib";
import { Clip, SEG, fit, speedLabel } from "../footage";
import { C, Chip, Frame, MONO } from "../theme";
import evs from "../push_rows.json";

const T = {
  start: f(ACTS.push[0]), strike: f(cue("Each strike")), row: f(cue("just one more row")), nothing: f(cue("Starting from nothing")),
  four: f(cue("four pushes")), icy: f(cue("make the table icy", 0)), over: f(cue("The first push overshoots")), notices: f(cue("The robot notices")),
  back: f(cue("back on target")), end: f(ACTS.push[1]),
};
// Pushes from the event log: [film-relative footage frame, puck→goal cm, after the icy change?]
const ROWS = evs as { f: number; cm: number; icy: boolean; surprise: boolean }[];
const SHOTS = [
  { file: "push.mp4", ...fit(T.start, T.icy, SEG.push0, SEG.goal1 + 25) },
  { file: "push.mp4", ...fit(T.icy, T.end, SEG.goal1 + 25, SEG.goal2 + 28) },
];
const srcAt = (fr: number) => { const s = SHOTS.find((x) => fr >= x.at && fr < x.at + x.dur) ?? SHOTS[1]; return s.src + (fr - s.at) * s.rate; };

export const Push: React.FC<{ fr: number }> = ({ fr }) => {
  const now = srcAt(fr);
  const shot = SHOTS.find((s) => fr >= s.at && fr < s.at + s.dur) ?? SHOTS[1];
  const done = ROWS.filter((r) => r.f <= now);
  const ice = prog(fr, T.icy, 20);
  return (
    <>
      <Frame label="Few-shot pushing" right={speedLabel(shot.rate)} style={{ left: 60, top: 60, width: 1220, height: 820 }}>
        {SHOTS.map((s, i) => <Clip key={i} file={s.file} at={s.at} dur={s.dur} src={s.src} rate={s.rate} />)}
        {/* frost on the table once it turns icy */}
        <div style={{ position: "absolute", inset: 0, background: `radial-gradient(ellipse at 50% 70%, rgba(191,233,255,${0.16 * ice}) 0%, rgba(191,233,255,0) 60%)`,
          boxShadow: `inset 0 0 160px rgba(191,233,255,${0.45 * ice})` }} />
      </Frame>
      {fr >= T.icy && <div style={{ position: "absolute", left: 90, top: 130 }}><Chip fr={fr} at={T.icy} color={C.ice} big>❄ icy table</Chip></div>}

      {/* every push is one more row */}
      <div style={{ position: "absolute", left: 1320, top: 90, width: 560, opacity: prog(fr, T.strike - 6, 14) }}>
        <div style={{ fontFamily: MONO, fontSize: 20, color: C.fg3, letterSpacing: 2, marginBottom: 10 }}>CONTEXT · ONE ROW PER PUSH</div>
        <div style={{ border: `1.5px solid ${C.line2}`, borderRadius: 14, background: C.panel, overflow: "hidden" }}>
          <div style={{ display: "grid", gridTemplateColumns: "70px 1fr 1fr", fontFamily: MONO, fontSize: 20, color: C.fg2, borderBottom: `1px solid ${C.line2}`, padding: "12px 16px" }}>
            <span>push</span><span>puck → goal</span><span>vs prediction</span>
          </div>
          {done.slice(-10).map((r) => {
            const i = ROWS.indexOf(r);
            const fresh = interpolate(now - r.f, [0, 30], [1, 0], clamp);
            const ok = r.cm <= 3;
            return (
              <div key={i} style={{ display: "grid", gridTemplateColumns: "70px 1fr 1fr", fontFamily: MONO, fontSize: 22, color: C.fg, padding: "10px 16px",
                borderBottom: `1px solid ${C.line}`, background: `rgba(245,165,36,${0.16 * fresh})` }}>
                <span style={{ color: r.icy ? C.ice : C.fg3 }}>{i + 1}</span>
                <span style={{ color: ok ? C.ok : C.fg }}>{r.cm.toFixed(1)} cm{ok ? " ✓" : ""}</span>
                <span style={{ color: r.surprise ? C.warn : C.fg3 }}>{r.surprise ? "surprise!" : "in range"}</span>
              </div>
            );
          })}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 14, marginTop: 22 }}>
          {fr >= T.four && <Chip fr={fr} at={T.four} color={C.ok}>median 4 pushes · 9 test goals</Chip>}
          {fr >= T.over && <Chip fr={fr} at={T.over} color={C.warn}>overshoot → surprise</Chip>}
          {fr >= T.back && <Chip fr={fr} at={T.back} color={C.ok}>back on target in 2–3</Chip>}
        </div>
      </div>
    </>
  );
};
