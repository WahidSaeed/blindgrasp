import React from "react";
import { loadFont as loadSans } from "@remotion/google-fonts/IBMPlexSans";
import { loadFont as loadMono } from "@remotion/google-fonts/JetBrainsMono";
import { interpolate } from "remotion";
import { clamp, pop, prog } from "./lib";

export const SANS = loadSans("normal", { weights: ["400", "500", "600", "700"], subsets: ["latin"] }).fontFamily;
export const MONO = loadMono("normal", { weights: ["400", "500", "700"], subsets: ["latin"] }).fontFamily;

// One meaning per colour for the whole film (same as the web UI):
// amber = what the robot touched/felt, cyan = what TabPFN predicts, green = success/goal, red = a surprise/change.
export const C = {
  bench: "#090a0c", panel: "#111316", panel2: "#171a1e", line: "#22262c", line2: "#2f343b",
  fg: "#e6e8eb", fg2: "#9ba2aa", fg3: "#626a73",
  touch: "#f5a524", model: "#3fb6e8", ok: "#4ccf72", warn: "#ff5a52", ice: "#bfe9ff",
};

export const Bg: React.FC = () => (
  <div style={{ position: "absolute", inset: 0, background: `radial-gradient(1500px 800px at 50% -200px, #161a21 0%, ${C.bench} 70%)` }}>
    <div style={{ position: "absolute", inset: 0, backgroundImage: "radial-gradient(rgba(255,255,255,0.05) 1px, transparent 1px)", backgroundSize: "28px 28px" }} />
  </div>
);

/** Small mono chip (label + optional dot), pops in at `at`. */
export const Chip: React.FC<{ fr: number; at: number; color?: string; children: React.ReactNode; style?: React.CSSProperties; big?: boolean }> = ({ fr, at, color = C.fg2, children, style, big }) => {
  const p = pop(fr, at);
  return (
    <div style={{ display: "inline-flex", alignItems: "center", gap: 12, padding: big ? "14px 22px" : "9px 16px", borderRadius: 999,
      background: "rgba(10,12,15,0.78)", border: `1.5px solid ${color}66`, color: C.fg, fontFamily: MONO, fontSize: big ? 30 : 22, fontWeight: 500,
      letterSpacing: 0.5, whiteSpace: "nowrap", backdropFilter: "blur(8px)", boxShadow: "0 12px 40px rgba(0,0,0,0.5)",
      opacity: interpolate(p, [0, 0.4], [0, 1], clamp), transform: `translateY(${(1 - p) * 14}px) scale(${0.92 + 0.08 * p})`, ...style }}>
      <span style={{ width: big ? 14 : 11, height: big ? 14 : 11, borderRadius: 99, background: color, boxShadow: `0 0 14px ${color}` }} />
      {children}
    </div>
  );
};

/** Big kinetic headline: words rise in one by one starting at `at`. */
export const Headline: React.FC<{ fr: number; at: number; text: string; size?: number; color?: string; accent?: Record<string, string>; style?: React.CSSProperties; stagger?: number }> = ({ fr, at, text, size = 84, color = C.fg, accent = {}, style, stagger = 3 }) => (
  <div style={{ fontFamily: SANS, fontWeight: 600, fontSize: size, lineHeight: 1.08, letterSpacing: -1.5, color, ...style }}>
    {text.split(" ").map((w, i) => {
      const p = prog(fr, at + i * stagger, 14);
      const key = w.replace(/[^\w]/g, "");
      return (
        <span key={i} style={{ display: "inline-block", marginRight: size * 0.26, opacity: p, transform: `translateY(${(1 - p) * size * 0.35}px)`, color: accent[key] ?? undefined }}>{w}</span>
      );
    })}
  </div>
);

/** A thin framed "monitor" for footage, lab-console style. */
export const Frame: React.FC<{ label: string; right?: React.ReactNode; children: React.ReactNode; style?: React.CSSProperties }> = ({ label, right, children, style }) => (
  <div style={{ position: "absolute", borderRadius: 18, overflow: "hidden", border: `1.5px solid ${C.line2}`, background: C.panel,
    boxShadow: "0 30px 80px -20px rgba(0,0,0,0.9), inset 0 1px 0 rgba(255,255,255,0.04)", ...style }}>
    <div style={{ height: 46, display: "flex", alignItems: "center", gap: 12, padding: "0 18px", borderBottom: `1px solid ${C.line}`, fontFamily: MONO, fontSize: 18, color: C.fg2 }}>
      <span style={{ width: 9, height: 9, borderRadius: 9, background: C.warn, boxShadow: `0 0 10px ${C.warn}` }} />
      {label}
      <span style={{ marginLeft: "auto" }}>{right}</span>
    </div>
    <div style={{ position: "absolute", top: 46, left: 0, right: 0, bottom: 0 }}>{children}</div>
  </div>
);

export const fadeIO = (fr: number, a: number, b: number, d = 10) =>
  Math.min(interpolate(fr, [a, a + d], [0, 1], clamp), interpolate(fr, [b - d, b], [1, 0], clamp));
