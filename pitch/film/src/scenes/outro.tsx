import React from "react";
import { interpolate } from "remotion";
import { ACTS, clamp, cue, f, prog } from "../lib";
import { Clip } from "../footage";
import { C, Chip, MONO, SANS } from "../theme";
import { Logo } from "./intro";

const T = {
  start: f(ACTS.outro[0]), move: f(cue("Move a box")), icy: f(cue("make the table icy", 1)), adapt: f(cue("watch it adapt")),
  robot: f(cue("A robot that learns")), inst: f(cue("Instantly")), final: f(cue("This is Blindgrasp", 1)), end: f(ACTS.outro[1]),
};

export const Outro: React.FC<{ fr: number }> = ({ fr }) => {
  const inP = prog(fr, T.start, 18);
  const out = interpolate(fr, [T.robot - 10, T.robot + 8], [1, 0], clamp);
  const card = prog(fr, T.robot, 18);
  return (
    <>
      {/* the real web app in a browser window */}
      <div style={{ position: "absolute", left: 160, top: 80, width: 1600, height: 900 + 46, opacity: inP * out,
        transform: `scale(${0.94 + 0.06 * inP - (1 - out) * 0.04})`, borderRadius: 18, overflow: "hidden", border: `1.5px solid ${C.line2}`, boxShadow: "0 40px 100px -20px rgba(0,0,0,0.95)" }}>
        <div style={{ height: 46, background: "#1b1e23", display: "flex", alignItems: "center", gap: 10, padding: "0 18px" }}>
          {["#ff5f57", "#febc2e", "#28c840"].map((c) => <span key={c} style={{ width: 14, height: 14, borderRadius: 14, background: c }} />)}
          <div style={{ marginLeft: 24, flex: 1, maxWidth: 700, height: 30, borderRadius: 8, background: "#0f1114", fontFamily: MONO, fontSize: 17, color: C.fg2, display: "flex", alignItems: "center", padding: "0 14px" }}>
            Blindgrasp · live in the browser
          </div>
        </div>
        <div style={{ position: "absolute", top: 46, left: 0, width: 1600, height: 900 }}>
          <Clip file="ui.mp4" at={T.start - 2} dur={T.robot - T.start + 12} src={30} />
        </div>
      </div>
      <div style={{ position: "absolute", right: 110, top: 120, display: "flex", flexDirection: "column", gap: 16, alignItems: "flex-end", opacity: out }}>
        {fr >= T.move && <Chip fr={fr} at={T.move} color={C.touch} big>move a box</Chip>}
        {fr >= T.icy && <Chip fr={fr} at={T.icy} color={C.ice} big>make it icy</Chip>}
        {fr >= T.adapt && <Chip fr={fr} at={T.adapt} color={C.ok} big>watch it adapt</Chip>}
      </div>

      {/* end card */}
      <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", opacity: card }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 30 }}>
          <Logo fr={fr} at={T.robot + 2} size={160} />
          <div style={{ fontFamily: SANS, fontSize: 46, color: C.fg, opacity: prog(fr, T.robot + 12, 14) }}>
            A robot that learns from every touch. <span style={{ color: C.model, opacity: prog(fr, T.inst, 10) }}>Instantly.</span>
          </div>
          <div style={{ display: "flex", gap: 16, marginTop: 20, opacity: prog(fr, T.final, 14) }}>
            {["TabPFN", "MuJoCo", "Franka Panda", "Next.js"].map((t) => (
              <span key={t} style={{ fontFamily: MONO, fontSize: 22, color: C.fg2, padding: "8px 16px", borderRadius: 99, border: `1px solid ${C.line2}` }}>{t}</span>
            ))}
          </div>
          <div style={{ fontFamily: MONO, fontSize: 28, color: C.fg2, marginTop: 10, opacity: prog(fr, T.final + 8, 14) }}>github.com/WahidSaeed/blindgrasp</div>
        </div>
      </div>
    </>
  );
};
