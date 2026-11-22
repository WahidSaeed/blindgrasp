import React from "react";
import { interpolate } from "remotion";
import { ACTS, clamp, cue, f, pop, prog } from "../lib";
import { Clip, SEG, speedLabel } from "../footage";
import { C, Chip, Frame, Headline, MONO, SANS, fadeIO } from "../theme";

const T = {
  start: f(ACTS.intro[0]), arm: f(cue("A Franka Panda")), nocam: f(cue("no camera at all")), probe: f(cue("Its only sense")),
  height: f(cue("feels a height")), job: f(cue("Its job")), push: f(cue("then push a puck")), end: f(ACTS.intro[1]),
};

export const Logo: React.FC<{ fr: number; at: number; size?: number }> = ({ fr, at, size = 150 }) => {
  const p = pop(fr, at, 16);
  const dots = [[0, 0, C.touch], [1, 0, C.fg2], [0, 1, C.fg2], [1, 1, C.model]] as const;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: size * 0.28, opacity: interpolate(p, [0, 0.3], [0, 1], clamp) }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: size * 0.1, transform: `scale(${0.6 + 0.4 * p})` }}>
        {dots.map(([, , c], i) => (
          <div key={i} style={{ width: size * 0.3, height: size * 0.3, borderRadius: size, background: c, boxShadow: `0 0 ${size * 0.2}px ${c}aa`,
            opacity: prog(fr, at + i * 3, 8) }} />
        ))}
      </div>
      <div style={{ fontFamily: SANS, fontWeight: 600, fontSize: size, letterSpacing: -size * 0.03, color: C.fg, transform: `translateX(${(1 - p) * 30}px)` }}>Blindgrasp</div>
    </div>
  );
};

export const Intro: React.FC<{ fr: number }> = ({ fr }) => {
  const titleOut = interpolate(fr, [T.arm - 8, T.arm + 4], [1, 0], clamp);
  const shot = prog(fr, T.arm - 6, 18);
  const h = interpolate(fr, [T.height, T.height + 24], [0, 6.0], clamp);
  return (
    <>
      <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", opacity: titleOut }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 26 }}>
          <Logo fr={fr} at={T.start + 2} />
          <div style={{ fontFamily: MONO, fontSize: 30, color: C.fg2, opacity: prog(fr, T.start + 14, 14) }}>a robot arm that learns its table by touch</div>
        </div>
      </div>

      <div style={{ opacity: shot, transform: `translateY(${(1 - shot) * 30}px)` }}>
        <Frame label="Franka Panda · MuJoCo simulation" right={speedLabel(1)} style={{ left: 70, top: 120, width: 1180, height: 710 }}>
          <Clip file="script2_hero.mp4" at={T.arm - 6} dur={T.end - T.arm + 6} src={SEG.intro ?? 0} />
          {/* the probe callout ring follows nothing fancy: it marks the tool area */}
        </Frame>
      </div>

      {/* right column */}
      <div style={{ position: "absolute", left: 1300, top: 150, width: 560, display: "flex", flexDirection: "column", gap: 22 }}>
        {fr >= T.nocam && (
          <Chip fr={fr} at={T.nocam} color={C.warn} big>
            <svg width="34" height="24" viewBox="0 0 24 16"><path d="M1 8s4-7 11-7 11 7 11 7-4 7-11 7S1 8 1 8z" stroke={C.fg} strokeWidth="1.6" fill="none" /><circle cx="12" cy="8" r="3" fill={C.fg} /><path d="M3 15 21 1" stroke={C.warn} strokeWidth="2.2" /></svg>
            no camera
          </Chip>
        )}
        {fr >= T.probe && (
          <div style={{ opacity: prog(fr, T.probe, 12), transform: `translateY(${(1 - prog(fr, T.probe, 12)) * 20}px)`, background: C.panel, border: `1.5px solid ${C.line2}`, borderRadius: 18, padding: 26 }}>
            <div style={{ fontFamily: MONO, fontSize: 20, color: C.fg3, letterSpacing: 2 }}>ONLY SENSE</div>
            <svg width="508" height="230" viewBox="0 0 508 230">
              {/* table + box */}
              <rect x="20" y="190" width="468" height="12" rx="3" fill="#cfc6b0" />
              <rect x="250" y="120" width="140" height="70" rx="4" fill="#d9579b" opacity="0.9" />
              {/* probe going down and touching the box */}
              {(() => {
                const d = interpolate(fr, [T.probe + 8, T.probe + 30, T.height, T.height + 10], [10, 40, 40, 108], clamp);
                const hit = fr >= T.height + 10;
                return (
                  <g>
                    <rect x="312" y={d - 90} width="16" height="90" rx="3" fill="#e8e8e8" />
                    <rect x="316" y={d} width="8" height="12" fill={C.touch} />
                    {hit && <circle cx="320" cy="120" r={8 + prog(fr, T.height + 10, 20) * 40} fill="none" stroke={C.touch} strokeWidth="3" opacity={1 - prog(fr, T.height + 10, 20)} />}
                    {hit && <circle cx="320" cy="120" r="7" fill={C.touch} />}
                  </g>
                );
              })()}
            </svg>
            <div style={{ display: "flex", justifyContent: "space-between", fontFamily: MONO, fontSize: 28, color: C.fg }}>
              <span>probe tip →</span>
              <span style={{ color: C.touch }}>height {h.toFixed(1)} cm</span>
            </div>
          </div>
        )}
      </div>

      {/* the job: two steps */}
      <div style={{ position: "absolute", left: 70, top: 870, display: "flex", gap: 24 }}>
        {[["1", "map the table", T.job, C.touch], ["2", "push the puck to the goal, around what it found", T.push, C.ok]].map(([n, txt, at, col]) => {
          const p = prog(fr, at as number, 14);
          return (
            <div key={n as string} style={{ opacity: p, transform: `translateY(${(1 - p) * 16}px)`, display: "flex", alignItems: "center", gap: 16, padding: "14px 24px",
              borderRadius: 14, border: `1.5px solid ${(col as string)}55`, background: "rgba(10,12,15,0.8)", fontFamily: SANS, fontSize: 32, color: C.fg }}>
              <span style={{ fontFamily: MONO, color: col as string, fontWeight: 700 }}>{n}</span>{txt as string}
            </div>
          );
        })}
      </div>
      <div style={{ display: "none" }}><Headline fr={fr} at={0} text="" /></div>
      <div style={{ opacity: fadeIO(fr, T.start, T.end) }} />
    </>
  );
};
