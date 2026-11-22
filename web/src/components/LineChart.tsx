"use client";

import { useEffect, useRef, useState } from "react";

export interface Series {
  points: { x: number; y: number | null; flag?: boolean }[];
  color: string;
}

interface Props {
  series: Series;
  target?: number;
  /** which side of the target is "good" */
  goodBelow?: boolean;
  yMax: number;
  xMin?: number;
  unit?: string;
  xLabel?: string;
  emptyLabel?: string;
}

/** Oscilloscope-style trace that fills its container. */
export function LineChart({ series, target, goodBelow = true, yMax, xMin = 40, unit = "", xLabel, emptyLabel }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 320, h: 140 });
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setSize({ w: Math.max(160, e.contentRect.width), h: Math.max(90, e.contentRect.height) }));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);

  const { w, h } = size;
  const L = 34, R = 10, T = 10, B = 20;
  const W = w - L - R, H = h - T - B;
  const pts = series.points.filter((p) => p.y != null) as { x: number; y: number; flag?: boolean }[];
  const xMax = Math.max(xMin, ...series.points.map((p) => p.x), 1);
  const X = (x: number) => L + (x / xMax) * W;
  const Y = (y: number) => T + H - (Math.min(Math.max(y, 0), yMax) / yMax) * H;
  const path = pts.map((p, i) => `${i ? "L" : "M"}${X(p.x).toFixed(1)},${Y(p.y).toFixed(1)}`).join(" ");
  const yt = [0, 0.25, 0.5, 0.75, 1].map((f) => f * yMax);
  const xt = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(f * xMax));
  const last = pts.at(-1);

  return (
    <div ref={ref} className="relative h-full w-full">
      <svg width={w} height={h} className="absolute inset-0 block font-mono">
        <rect x={L} y={T} width={W} height={H} fill="var(--color-well)" />
        {target != null && (
          <rect x={L} width={W} y={goodBelow ? Y(target) : T} height={goodBelow ? T + H - Y(target) : Y(target) - T} fill="rgb(76 207 114 / 0.06)" />
        )}
        {yt.map((v) => (
          <g key={`y${v}`}>
            <line x1={L} x2={L + W} y1={Y(v)} y2={Y(v)} stroke="var(--color-line)" strokeDasharray={v ? "2 3" : undefined} />
            <text x={L - 6} y={Y(v) + 3} textAnchor="end" fontSize={9.5} fill="var(--color-fg-3)">
              {Number.isInteger(v) ? v : v.toFixed(yMax > 2 ? 1 : 2)}
            </text>
          </g>
        ))}
        {xt.map((v, i) => (
          <g key={`x${i}`}>
            <line x1={X(v)} x2={X(v)} y1={T} y2={T + H} stroke="var(--color-line)" strokeDasharray={i ? "2 3" : undefined} />
            <text x={X(v)} y={h - 6} textAnchor={i === 0 ? "start" : i === 4 ? "end" : "middle"} fontSize={9.5} fill="var(--color-fg-3)">
              {i === 2 && xLabel ? `${v} ${xLabel}` : v}
            </text>
          </g>
        ))}
        {target != null && (
          <g>
            <line x1={L} x2={L + W} y1={Y(target)} y2={Y(target)} stroke="var(--color-ok)" strokeWidth={1} strokeDasharray="5 3" />
            <text x={L + W - 4} y={Y(target) - 4} textAnchor="end" fontSize={9.5} fill="var(--color-ok)">
              target {goodBelow ? "<" : ">"} {target}
              {unit}
            </text>
          </g>
        )}
        {path && (
          <>
            <path d={path} fill="none" stroke={series.color} strokeWidth={4} strokeOpacity={0.15} strokeLinejoin="round" />
            <path d={path} fill="none" stroke={series.color} strokeWidth={1.5} strokeLinejoin="round" />
          </>
        )}
        {pts.length <= 60 && pts.map((p, i) => <circle key={i} cx={X(p.x)} cy={Y(p.y)} r={1.8} fill={series.color} />)}
        {pts.filter((p) => p.flag).map((p, i) => (
          <g key={`f${i}`}>
            <line x1={X(p.x)} x2={X(p.x)} y1={T} y2={T + H} stroke="var(--color-warn)" strokeWidth={1} strokeDasharray="3 2" />
            <rect x={X(p.x) + 3} y={T + 2} width={44} height={13} fill="var(--color-warn)" />
            <text x={X(p.x) + 6} y={T + 11.5} fontSize={9} fontWeight={600} fill="#140808">CHANGE</text>
          </g>
        ))}
        {last && (
          <g>
            <circle cx={X(last.x)} cy={Y(last.y)} r={3.5} fill={series.color} />
            <circle cx={X(last.x)} cy={Y(last.y)} r={7} fill="none" stroke={series.color} strokeOpacity={0.4} />
          </g>
        )}
      </svg>
      {!pts.length && emptyLabel && (
        <div className="absolute inset-0 grid place-items-center">
          <span className="font-mono text-[11px] text-fg-3">— {emptyLabel} —</span>
        </div>
      )}
    </div>
  );
}
