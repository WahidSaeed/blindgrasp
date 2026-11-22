import React from "react";
import { interpolate, random } from "remotion";
import { ACTS, clamp, cue, f, pop, prog } from "../lib";
import { C, Chip, Headline, MONO, SANS } from "../theme";

const T = {
  start: f(ACTS.brain[0]), found: f(cue("a foundation model")), never: f(cue("it never trains")), single: f(cue("not a single")),
  row: f(cue("Every touch becomes")), xyh: f(cue("X, y, height")), next: f(cue("The very next prediction")),
  unsure: f(cue("also says how unsure")), least: f(cue("least certain")), end: f(ACTS.brain[1]),
};

// The table, seen from above: 30 x 20 cells; three boxes with their real heights (cm).
const W = 30, H = 20, CELL = 30;
const BOXES = [{ x0: 3, x1: 11, y0: 2, y1: 8, h: 8 }, { x0: 15, x1: 22, y0: 10, y1: 18, h: 12 }, { x0: 21, x1: 28, y0: 2, y1: 8, h: 6 }];
const truth = (x: number, y: number) => BOXES.find((b) => x >= b.x0 && x < b.x1 && y >= b.y0 && y < b.y1)?.h ?? 0;

// Touch sequence: a few scattered, then always the least-certain spot (farthest from every touch so far).
const TOUCHES: { x: number; y: number; h: number }[] = [];
for (let i = 0; i < 4; i++) { const x = Math.floor(3 + random(`t${i}x`) * 24), y = Math.floor(2 + random(`t${i}y`) * 16); TOUCHES.push({ x, y, h: truth(x, y) }); }
while (TOUCHES.length < 70) {
  let best = { x: 0, y: 0, d: -1 };
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const d = Math.min(...TOUCHES.map((t) => (t.x - x) ** 2 + (t.y - y) ** 2)) + random(`j${x},${y}`) * 0.5;
    if (d > best.d) best = { x, y, d };
  }
  TOUCHES.push({ x: best.x, y: best.y, h: truth(best.x, best.y) });
}
// When each touch lands: slow at first (one row at a time, readable), then faster.
const TIMES: number[] = [];
{ let t = T.row + 4; for (let i = 0; i < TOUCHES.length; i++) { TIMES.push(t); t += i < 4 ? Math.round((T.xyh + 20 - T.row) / 4) : i < 10 ? 10 : 4; } }

const predict = (n: number) => {
  const pts = TOUCHES.slice(0, n);
  const pred: number[] = [], unc: number[] = [];
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    if (!pts.length) { pred.push(0); unc.push(1); continue; }
    const ds = pts.map((p) => ({ d: (p.x - x) ** 2 + (p.y - y) ** 2, h: p.h })).sort((a, b) => a.d - b.d).slice(0, 4);
    let sw = 0, sh = 0;
    for (const { d, h } of ds) { const w = 1 / (d + 0.3) ** 2; sw += w; sh += w * h; }
    pred.push(sh / sw);
    unc.push(Math.min(1, Math.sqrt(ds[0].d) / 6));
  }
  return { pred, unc };
};

export const Brain: React.FC<{ fr: number }> = ({ fr }) => {
  const n = TIMES.filter((t) => fr >= t).length;
  const { pred, unc } = predict(n);
  const showUnc = prog(fr, T.unsure, 16);
  const nextT = TOUCHES[n];
  const lastAt = n ? TIMES[n - 1] : -99;
  const flash = n ? 1 - prog(fr, lastAt, 12) : 0;
  const tableIn = prog(fr, T.row - 6, 14);
  const rows = TOUCHES.slice(0, n).slice(-9);
  const MAPX = 930, MAPY = 230;
  return (
    <>
      {/* title */}
      <div style={{ position: "absolute", left: 90, top: 80, display: "flex", alignItems: "center", gap: 22 }}>
        <Chip fr={fr} at={T.start + 2} color={C.model} big>TabPFN</Chip>
        <div style={{ fontFamily: SANS, fontSize: 36, color: C.fg2, opacity: prog(fr, T.found, 12) }}>a foundation model for tables</div>
      </div>

      {/* gradient steps: 0 */}
      <div style={{ position: "absolute", left: 90, top: 170, display: "flex", alignItems: "baseline", gap: 20, opacity: prog(fr, T.never, 12) }}>
        <span style={{ fontFamily: MONO, fontSize: 30, color: C.fg2 }}>training steps</span>
        <span style={{ fontFamily: MONO, fontSize: 96, fontWeight: 700, color: C.fg, transform: `scale(${1 + 0.25 * (1 - prog(fr, T.single, 14)) * (fr >= T.single ? 1 : 0)})`, display: "inline-block" }}>0</span>
        <span style={{ fontFamily: SANS, fontSize: 30, color: C.fg3, opacity: prog(fr, T.single + 6, 12) }}>no gradient descent, ever</span>
      </div>

      {/* context table */}
      <div style={{ position: "absolute", left: 90, top: 330, width: 720, opacity: tableIn, transform: `translateY(${(1 - tableIn) * 20}px)` }}>
        <div style={{ fontFamily: MONO, fontSize: 20, color: C.fg3, letterSpacing: 2, marginBottom: 10 }}>CONTEXT · {n} ROWS</div>
        <div style={{ border: `1.5px solid ${C.line2}`, borderRadius: 14, overflow: "hidden", background: C.panel }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", fontFamily: MONO, fontSize: 26, color: C.fg2, borderBottom: `1px solid ${C.line2}` }}>
            {["x", "y", "height"].map((h, i) => {
              const hl = fr >= T.xyh + i * 7 && fr < T.next ? 1 : 0;
              return <div key={h} style={{ padding: "14px 22px", color: hl ? C.touch : C.fg2, background: hl ? "rgba(245,165,36,0.12)" : "transparent" }}>{h}</div>;
            })}
          </div>
          <div style={{ height: 9 * 46, position: "relative" }}>
            {rows.map((r, i) => {
              const idx = n - rows.length + i;
              const p = prog(fr, TIMES[idx], 10);
              const isNew = idx === n - 1;
              return (
                <div key={idx} style={{ position: "absolute", left: 0, right: 0, top: i * 46, height: 46, display: "grid", gridTemplateColumns: "1fr 1fr 1fr",
                  fontFamily: MONO, fontSize: 24, color: C.fg, alignItems: "center", opacity: p, transform: `translateX(${(1 - p) * -40}px)`,
                  background: isNew ? `rgba(245,165,36,${0.18 * (1 - prog(fr, TIMES[idx] + 6, 20))})` : "transparent", borderBottom: `1px solid ${C.line}` }}>
                  <div style={{ padding: "0 22px" }}>{(0.2 + r.x * 0.018).toFixed(2)}</div>
                  <div style={{ padding: "0 22px" }}>{(-0.18 + r.y * 0.018).toFixed(2)}</div>
                  <div style={{ padding: "0 22px", color: r.h > 0 ? C.touch : C.fg2 }}>{r.h.toFixed(1)} cm</div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* arrow table -> map */}
      <svg width="1920" height="1080" style={{ position: "absolute", inset: 0, opacity: tableIn }}>
        <path d={`M 830 560 C 870 560, 880 540, ${MAPX - 20} 540`} stroke={C.model} strokeWidth={3} fill="none" strokeDasharray="8 8" strokeDashoffset={-fr * 1.5} opacity={0.4 + flash * 0.6} />
      </svg>

      {/* the predicted map */}
      <div style={{ position: "absolute", left: MAPX, top: MAPY - 60, fontFamily: MONO, fontSize: 20, color: C.fg3, letterSpacing: 2, opacity: tableIn }}>
        PREDICTED MAP <span style={{ color: C.model }}>· blue = TabPFN's guess</span> <span style={{ color: C.fg3 }}>· illustration</span>
      </div>
      <svg width={W * CELL} height={H * CELL} style={{ position: "absolute", left: MAPX, top: MAPY, opacity: tableIn, borderRadius: 12, background: "#0c1014", outline: `1.5px solid ${C.line2}` }}>
        {pred.map((v, i) => {
          const x = i % W, y = Math.floor(i / W);
          const u = unc[i] * showUnc;
          const lum = 0.18 + (v / 12) * 0.82;
          return <rect key={i} x={x * CELL + 1} y={y * CELL + 1} width={CELL - 2} height={CELL - 2} rx={4}
            fill={`rgba(63,182,232,${(lum * (1 - u * 0.85)) * (n ? 1 : 0.15) + flash * 0.05})`} />;
        })}
        {/* uncertainty haze */}
        {showUnc > 0 && pred.map((_, i) => {
          const u = unc[i]; const x = i % W, y = Math.floor(i / W);
          return u > 0.45 ? <rect key={`u${i}`} x={x * CELL + 1} y={y * CELL + 1} width={CELL - 2} height={CELL - 2} rx={4} fill="none" stroke={C.fg3} strokeDasharray="3 4" opacity={showUnc * (u - 0.45) * 1.6} /> : null;
        })}
        {/* touches */}
        {TOUCHES.slice(0, n).map((t, i) => {
          const p = prog(fr, TIMES[i], 16);
          return (
            <g key={i}>
              <circle cx={t.x * CELL + CELL / 2} cy={t.y * CELL + CELL / 2} r={6} fill={t.h > 0 ? C.touch : "#b8bec6"} />
              {p < 1 && <circle cx={t.x * CELL + CELL / 2} cy={t.y * CELL + CELL / 2} r={6 + p * 40} fill="none" stroke={C.touch} strokeWidth={3} opacity={1 - p} />}
            </g>
          );
        })}
        {/* next touch: the least certain spot */}
        {showUnc > 0 && nextT && (
          <g opacity={showUnc} transform={`translate(${nextT.x * CELL + CELL / 2} ${nextT.y * CELL + CELL / 2})`}>
            <circle r={22 + 4 * Math.sin(fr / 4)} fill="none" stroke={C.fg} strokeWidth={2.5} />
            <path d="M -32 0 H -14 M 14 0 H 32 M 0 -32 V -14 M 0 14 V 32" stroke={C.fg} strokeWidth={2.5} />
          </g>
        )}
      </svg>
      {showUnc > 0 && (
        <div style={{ position: "absolute", left: MAPX, top: MAPY + H * CELL + 22, display: "flex", gap: 18 }}>
          <Chip fr={fr} at={T.unsure + 4} color={C.fg3}>dashed = unsure</Chip>
          <Chip fr={fr} at={T.least} color={C.fg}>⌖ next touch: least certain spot</Chip>
        </div>
      )}
      <div style={{ display: "none" }}>{interpolate(0, [0, 1], [0, 1], clamp)}{pop(0, 0)}<Headline fr={0} at={0} text="" /></div>
    </>
  );
};
