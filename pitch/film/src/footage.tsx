import React from "react";
import { OffthreadVideo, Sequence, staticFile } from "remotion";
import seg from "./segments.json";

// Footage = offline MuJoCo renders at SIM_SPEED sim-seconds per video second (pitch/footage/*.mp4).
export const SIM_SPEED = 3;
export const SEG = seg as Record<string, number>;   // named footage frames picked from the per-frame event log

/** Plays `file` from footage frame `src` starting at film frame `at`, at `rate`x; fills its parent. */
export const Clip: React.FC<{ file: string; at: number; dur: number; src: number; rate?: number; style?: React.CSSProperties }> = ({ file, at, dur, src, rate = 1, style }) => (
  <Sequence from={at} durationInFrames={dur} layout="none">
    <OffthreadVideo src={staticFile(file)} startFrom={Math.max(0, Math.round(src))} playbackRate={rate} muted
      style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", ...style }} />
  </Sequence>
);

/** Shown speed relative to real time. */
export const speedLabel = (rate: number) => `${+(SIM_SPEED * rate).toFixed(1)}× speed`;

/** A shot that maps film frames [a, b) onto footage frames [sa, sb): the rate is whatever fits, capped. */
export const fit = (a: number, b: number, sa: number, sb: number, max = 6) => ({ at: a, dur: b - a, src: sa, rate: Math.min(max, Math.max(0.5, (sb - sa) / (b - a))) });
