import React from "react";
import { Img, interpolate, random, staticFile } from "remotion";
import { clamp, cue, f, prog } from "../lib";
import { C, Headline, MONO, fadeIO } from "../theme";

const T = {
  dust: f(cue("Dust")), dark: f(cue("darkness")), grip: f(cue("gripper")), what: f(cue("So what if")),
  switch: f(cue("light switch")), touch: f(cue("By touch")), end: f(cue("This is Blindgrasp", 0)),
};
// Where the touches land (fraction of the 1920x1080 frame) and when, after "By touch".
const TOUCHES = [[0.5, 0.52], [0.36, 0.6], [0.63, 0.44], [0.46, 0.36], [0.58, 0.66], [0.28, 0.45], [0.72, 0.58], [0.52, 0.22]].map(
  ([x, y], i) => ({ x: x * 1920, y: y * 1080, at: T.touch + 3 + i * 3 }));

export const Hook: React.FC<{ fr: number }> = ({ fr }) => {
  const fog = prog(fr, T.dust, 30);
  const dim = prog(fr, T.dark, 24);
  const block = prog(fr, T.grip, 16);
  const camOut = interpolate(fr, [T.what - 6, T.what + 6], [1, 0], clamp);
  return (
    <>
      {/* 1. the camera's view, failing */}
      <div style={{ position: "absolute", inset: 0, opacity: camOut }}>
        <div style={{ position: "absolute", left: 210, top: 110, width: 1500, height: 844, overflow: "hidden", borderRadius: 8 }}>
          <Img src={staticFile("hero_still.jpg")} style={{ width: "100%", height: "100%", objectFit: "cover",
            filter: `blur(${fog * 7}px) brightness(${1 - dim * 0.82}) saturate(${1 - fog * 0.5})`, transform: `scale(${1.04 + fr * 0.0006})` }} />
          {/* dust */}
          {Array.from({ length: 140 }).map((_, i) => {
            const x = random(`dx${i}`) * 1500, y = (random(`dy${i}`) * 844 + fr * (0.6 + random(`ds${i}`) * 1.4)) % 844;
            const r = 2 + random(`dr${i}`) * 7;
            return <div key={i} style={{ position: "absolute", left: x, top: y, width: r, height: r, borderRadius: r, background: "#d9cdb8", opacity: fog * (0.25 + random(`do${i}`) * 0.5), filter: "blur(1px)" }} />;
          })}
          <div style={{ position: "absolute", inset: 0, background: `rgba(200,190,170,${fog * 0.22})` }} />
          {/* the gripper sliding over the lens */}
          <div style={{ position: "absolute", top: -40, bottom: -40, width: 1700, left: interpolate(block, [0, 1], [1600, -100]), borderRadius: 400,
            background: "radial-gradient(ellipse at 30% 50%, #2a2d31 0%, #0c0d0f 70%)" }} />
          {/* static once blocked */}
          <svg style={{ position: "absolute", inset: 0, opacity: interpolate(block, [0.7, 1], [0, 0.35], clamp) }} width="1500" height="844">
            <filter id="st"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="1" seed={fr % 50} /></filter>
            <rect width="1500" height="844" filter="url(#st)" />
          </svg>
          <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", opacity: interpolate(block, [0.8, 1], [0, 1], clamp) }}>
            <div style={{ fontFamily: MONO, fontSize: 54, color: C.warn, letterSpacing: 6, textShadow: `0 0 24px ${C.warn}` }}>NO SIGNAL</div>
          </div>
        </div>
        {/* viewfinder chrome */}
        <svg width="1920" height="1080" style={{ position: "absolute", inset: 0 }}>
          {[[210, 110, 1, 1], [1710, 110, -1, 1], [210, 954, 1, -1], [1710, 954, -1, -1]].map(([x, y, sx, sy], i) => (
            <path key={i} d={`M${x} ${y + sy * 60} V${y} H${x + sx * 60}`} stroke={C.fg} strokeWidth={4} fill="none" opacity={0.85} />
          ))}
        </svg>
        <div style={{ position: "absolute", left: 250, top: 140, fontFamily: MONO, fontSize: 26, color: C.fg, display: "flex", gap: 14, alignItems: "center" }}>
          <span style={{ width: 16, height: 16, borderRadius: 16, background: C.warn, opacity: Math.floor(fr / 15) % 2 ? 1 : 0.25 }} /> CAM 1 · REC
        </div>
        <div style={{ position: "absolute", right: 250, top: 140, fontFamily: MONO, fontSize: 26, color: block > 0.8 ? C.warn : C.fg2 }}>
          {block > 0.8 ? "camera blocked" : dim > 0.5 ? "low light" : fog > 0.4 ? "dust on lens" : "vision ok"}
        </div>
      </div>

      {/* 2. the question */}
      <div style={{ position: "absolute", left: 0, right: 0, top: 380, textAlign: "center", opacity: fadeIO(fr, T.what, T.touch + 2, 8) }}>
        <Headline fr={fr} at={T.what} text="What if it learned its table" size={80} style={{ display: "inline-block" }} />
        <br />
        <Headline fr={fr} at={T.switch - 4} text="in the dark?" size={80} color={C.fg2} style={{ display: "inline-block", marginTop: 12 }} />
      </div>

      {/* 3. by touch: every touch reveals a patch of the table */}
      <svg width="1920" height="1080" style={{ position: "absolute", inset: 0 }}>
        <defs>
          <mask id="reveal">
            <rect width="1920" height="1080" fill="black" />
            {TOUCHES.map((t, i) => {
              const p = prog(fr, t.at, 26);
              return <circle key={i} cx={t.x} cy={t.y} r={p * 230} fill="white" style={{ filter: "blur(22px)" }} />;
            })}
          </mask>
        </defs>
        <image href={staticFile("hero_still.jpg")} x="0" y="0" width="1920" height="1080" preserveAspectRatio="xMidYMid slice" mask="url(#reveal)" />
        {TOUCHES.map((t, i) => {
          const p = prog(fr, t.at, 26);
          return fr >= t.at ? (
            <g key={i}>
              <circle cx={t.x} cy={t.y} r={10 + p * 120} fill="none" stroke={C.touch} strokeWidth={4} opacity={1 - p} />
              <circle cx={t.x} cy={t.y} r={9} fill={C.touch} style={{ filter: `drop-shadow(0 0 12px ${C.touch})` }} />
            </g>
          ) : null;
        })}
      </svg>
      <div style={{ position: "absolute", left: 0, right: 0, top: 120, textAlign: "center", opacity: fadeIO(fr, T.touch, T.end + 10, 6) }}>
        <Headline fr={fr} at={T.touch} text="By touch." size={110} color={C.touch} style={{ display: "inline-block", textShadow: "0 6px 30px rgba(0,0,0,0.8)" }} />
      </div>
    </>
  );
};
