"use client";

import { useEffect, useRef, useState } from "react";

export interface Series {
  points: { x: number; y: number | null; flag?: boolean }[];
  color: string;
}

interface Props {
  series: Series;
  target?: number;
  /** where the "good" side of the target is */
  goodBelow?: boolean;
  yMax: number;
  xMin?: number;
  unit?: string;
  height?: number;
  emptyLabel?: string;
}

/** Small responsive SVG line chart with a dashed target line, a shaded "good" zone and red flag markers. */
export function LineChart({ series, target, goodBelow = true, yMax, xMin = 40, unit = "", height = 150, emptyLabel }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(320);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(160, e.contentRect.width)));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);

  const L = 34, R = 10, T = 10, B = 22;
  const W = w - L - R, H = height - T - B;
  const pts = series.points.filter((p) => p.y != null) as { x: number; y: number; flag?: boolean }[];
  const xMax = Math.max(xMin, ...series.points.map((p) => p.x), 1);
  const X = (x: number) => L + (x / xMax) * W;
  const Y = (y: number) => T + H - (Math.min(Math.max(y, 0), yMax) / yMax) * H;
  const path = pts.map((p, i) => `${i ? "L" : "M"}${X(p.x).toFixed(1)},${Y(p.y).toFixed(1)}`).join(" ");
  const area = pts.length
    ? `${path} L${X(pts[pts.length - 1].x).toFixed(1)},${(T + H).toFixed(1)} L${X(pts[0].x).toFixed(1)},${(T + H).toFixed(1)} Z`
    : "";
  const gid = `g-${series.color.replace(/[^a-z0-9]/gi, "")}`;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * yMax);

  return (
    <div ref={ref} className="relative w-full">
      <svg width={w} height={height} className="block overflow-visible">
        <defs>
          <linearGradient id={gid} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={series.color} stopOpacity={0.28} />
            <stop offset="100%" stopColor={series.color} stopOpacity={0} />
          </linearGradient>
        </defs>
        {target != null && (
          <rect
            x={L}
            width={W}
            y={goodBelow ? Y(target) : T}
            height={goodBelow ? T + H - Y(target) : Y(target) - T}
            fill="rgb(52 211 153 / 0.06)"
          />
        )}
        {ticks.map((v) => (
          <g key={v}>
            <line x1={L} x2={L + W} y1={Y(v)} y2={Y(v)} stroke="rgb(255 255 255 / 0.06)" />
            <text x={L - 6} y={Y(v) + 3} textAnchor="end" className="fill-zinc-500 text-[10px] tabular-nums">
              {Number.isInteger(v) ? v : v.toFixed(yMax > 2 ? 1 : 2)}
            </text>
          </g>
        ))}
        <text x={L} y={height - 6} className="fill-zinc-500 text-[10px]">0</text>
        <text x={L + W} y={height - 6} textAnchor="end" className="fill-zinc-500 text-[10px] tabular-nums">{xMax}</text>
        {target != null && (
          <g>
            <line x1={L} x2={L + W} y1={Y(target)} y2={Y(target)} stroke="rgb(52 211 153 / 0.8)" strokeDasharray="4 4" />
            <text x={L + W} y={Y(target) - 4} textAnchor="end" className="fill-emerald-400 text-[10px]">
              target {target}
              {unit}
            </text>
          </g>
        )}
        {area && <path d={area} fill={`url(#${gid})`} />}
        {path && <path d={path} fill="none" stroke={series.color} strokeWidth={2} strokeLinejoin="round" />}
        {pts.map((p, i) => (
          <circle key={i} cx={X(p.x)} cy={Y(p.y)} r={pts.length > 60 ? 0 : 2.2} fill={series.color} />
        ))}
        {pts.filter((p) => p.flag).map((p, i) => (
          <g key={`f${i}`}>
            <circle cx={X(p.x)} cy={Y(p.y)} r={9} fill="rgb(244 63 94 / 0.18)" />
            <circle cx={X(p.x)} cy={Y(p.y)} r={4.5} fill="rgb(244 63 94)" stroke="#0b0d11" strokeWidth={1.5} />
          </g>
        ))}
        {pts.length > 0 && (
          <circle cx={X(pts[pts.length - 1].x)} cy={Y(pts[pts.length - 1].y)} r={4} fill={series.color} className="animate-pulse" />
        )}
      </svg>
      {!pts.length && emptyLabel && (
        <div className="absolute inset-0 flex items-center justify-center text-xs text-zinc-500">{emptyLabel}</div>
      )}
    </div>
  );
}
