import React from "react";
import { interpolate, random } from "remotion";
import { ACTS, clamp, cue, f, prog } from "../lib";
import { C, Chip, MONO, SANS } from "../theme";

const T = {
  start: f(ACTS.results[0]), gp: f(cue("a Gaussian process", 0)), nn: f(cue("nearest neighbours")), seeds: f(cue("three seeds")),
  heights: f(cue("TabPFN mapped heights")), six: f(cue("about six")), fewer: f(cue("needed fewer pushes")), four: f(cue("four instead")),
  limit: f(cue("And we measured")), eighty: f(cue("With eighty touches")), notl: f(cue("not by the learner")), end: f(ACTS.results[1]),
};
// Measured (eval/out/map_tabpfn_vs_baselines.json, push_tabpfn_vs_gp.json): 3 seeds, 80 touches; medians of pushes.
const HEIGHT = [{ k: "TabPFN", v: 0.62, c: C.model }, { k: "nearest neighbours", v: 0.62, c: C.fg3 }, { k: "Gaussian process", v: 0.83, c: C.fg3 }];
const PUSHES = [{ k: "TabPFN", v: 4, c: C.model }, { k: "Gaussian process", v: 5, c: C.fg3 }];

const Card: React.FC<{ title: string; sub: string; at: number; fr: number; x: number; children: React.ReactNode }> = ({ title, sub, at, fr, x, children }) => {
  const p = prog(fr, at, 16);
  return (
    <div style={{ position: "absolute", left: x, top: 250, width: 800, height: 520, padding: 36, borderRadius: 20, background: C.panel, border: `1.5px solid ${C.line2}`,
      opacity: p, transform: `translateY(${(1 - p) * 30}px)` }}>
      <div style={{ fontFamily: SANS, fontSize: 36, fontWeight: 600, color: C.fg }}>{title}</div>
      <div style={{ fontFamily: MONO, fontSize: 20, color: C.fg3, marginTop: 6, marginBottom: 34 }}>{sub}</div>
      {children}
    </div>
  );
};

export const Results: React.FC<{ fr: number }> = ({ fr }) => {
  const limitIn = prog(fr, T.limit - 4, 16);
  const chartsOut = 1 - limitIn;
  return (
    <>
      <div style={{ position: "absolute", left: 120, top: 90, display: "flex", gap: 18, alignItems: "center", opacity: chartsOut }}>
        <Chip fr={fr} at={T.start + 2} color={C.model} big>TabPFN</Chip>
        <span style={{ fontFamily: SANS, fontSize: 34, color: C.fg3, opacity: prog(fr, T.gp - 4, 10) }}>vs</span>
        {fr >= T.gp && <Chip fr={fr} at={T.gp} big>Gaussian process</Chip>}
        {fr >= T.nn && <Chip fr={fr} at={T.nn} big>nearest neighbours</Chip>}
        {fr >= T.seeds && <Chip fr={fr} at={T.seeds} color={C.fg3}>3 seeds each</Chip>}
      </div>

      <div style={{ opacity: chartsOut }}>
        <Card fr={fr} at={T.heights} x={120} title="Map height error" sub="after 80 touches · lower is better">
          {HEIGHT.map((b, i) => {
            const p = prog(fr, T.heights + 8 + i * 6, 26);
            const w = (b.v / 0.9) * 380 * p;
            return (
              <div key={b.k} style={{ display: "flex", alignItems: "center", gap: 18, marginBottom: 34 }}>
                <div style={{ width: 230, flexShrink: 0, fontFamily: SANS, fontSize: 26, color: b.c === C.model ? C.fg : C.fg2, textAlign: "right" }}>{b.k}</div>
                <div style={{ height: 54, width: w, borderRadius: 8, background: b.c, boxShadow: b.c === C.model ? `0 0 26px ${C.model}66` : undefined }} />
                <div style={{ whiteSpace: "nowrap", fontFamily: MONO, fontSize: 30, color: b.c === C.model ? C.model : C.fg2, opacity: prog(fr, T.six - 6 + i * 4, 10) }}>{(b.v * 10).toFixed(0)} mm</div>
              </div>
            );
          })}
        </Card>
        <Card fr={fr} at={T.fewer - 6} x={1000} title="Pushes to reach the goal" sub="median, starting from nothing · lower is better">
          {PUSHES.map((b, i) => (
            <div key={b.k} style={{ display: "flex", alignItems: "center", gap: 18, marginBottom: 50 }}>
              <div style={{ width: 230, flexShrink: 0, fontFamily: SANS, fontSize: 26, color: b.c === C.model ? C.fg : C.fg2, textAlign: "right" }}>{b.k}</div>
              <div style={{ display: "flex", gap: 14 }}>
                {Array.from({ length: b.v }).map((_, j) => {
                  const p = prog(fr, T.fewer + 4 + i * 10 + j * 4, 10);
                  return <div key={j} style={{ width: 54, height: 54, borderRadius: 54, background: b.c === C.model ? C.model : "#3a4048", transform: `scale(${p})`,
                    boxShadow: b.c === C.model ? `0 0 18px ${C.model}88` : undefined, border: "3px solid rgba(255,255,255,0.15)" }} />;
                })}
              </div>
              <div style={{ fontFamily: MONO, fontSize: 34, color: b.c === C.model ? C.model : C.fg2, opacity: prog(fr, T.four + i * 8, 10) }}>{b.v}</div>
            </div>
          ))}
          <div style={{ fontFamily: MONO, fontSize: 22, color: C.fg3, marginTop: 6 }}>after the table turns icy: 2–3 pushes</div>
        </Card>
      </div>

      {/* the honest limit */}
      <div style={{ position: "absolute", inset: 0, opacity: limitIn }}>
        <div style={{ position: "absolute", left: 160, top: 170, fontFamily: MONO, fontSize: 24, color: C.warn, letterSpacing: 3 }}>THE LIMIT, MEASURED</div>
        <div style={{ position: "absolute", left: 160, top: 220, width: 760, fontFamily: SANS, fontSize: 58, fontWeight: 600, lineHeight: 1.12, color: C.fg }}>
          Box outlines are capped by <span style={{ color: C.touch }}>how many points you touch</span>
          <span style={{ color: C.fg2, opacity: prog(fr, T.notl, 12) }}>, not by the learner.</span>
        </div>
        <div style={{ position: "absolute", left: 160, top: 640, width: 740, fontFamily: MONO, fontSize: 24, lineHeight: 1.5, color: C.fg2, opacity: prog(fr, T.notl + 10, 14) }}>
          every learner lands at a similar outline score (IoU ≈ 0.3–0.4) with 80 touches
        </div>
        {/* 80 touches on a box: the outline can only be as sharp as the dots */}
        <svg width="760" height="560" style={{ position: "absolute", left: 1020, top: 190 }}>
          <rect x="0" y="0" width="760" height="560" rx="18" fill={C.panel} stroke={C.line2} strokeWidth="1.5" />
          <rect x="250" y="160" width="270" height="220" fill="none" stroke={C.fg} strokeWidth="3" strokeDasharray="10 8" opacity="0.7" />
          {Array.from({ length: 80 }).map((_, i) => {
            const x = 40 + random(`r${i}x`) * 680, y = 40 + random(`r${i}y`) * 480;
            const inside = x > 250 && x < 520 && y > 160 && y < 380;
            const p = prog(fr, T.eighty + i * 0.6, 8);
            return <circle key={i} cx={x} cy={y} r={7 * p} fill={inside ? C.touch : "#8a9098"} />;
          })}
          <text x="380" y="140" textAnchor="middle" fill={C.fg2} fontFamily={MONO} fontSize="22">real box</text>
          <text x="380" y="530" textAnchor="middle" fill={C.touch} fontFamily={MONO} fontSize="24" opacity={prog(fr, T.eighty + 50, 10)}>80 touches</text>
        </svg>
      </div>
      <div style={{ display: "none" }}>{interpolate(0, [0, 1], [0, 1], clamp)}</div>
    </>
  );
};
