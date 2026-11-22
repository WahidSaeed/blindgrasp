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
  height?: number;
  xLabel?: string;
  emptyLabel?: string;
}

/** A plot on graph paper: ink line, hand-set target line, circled "change" marks. */
export function LineChart({ series, target, goodBelow = true, yMax, xMin = 40, unit = "", height = 170, xLabel, emptyLabel }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(320);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(160, e.contentRect.width)));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);

  const L = 36, R = 12, T = 12, B = 26;
  const W = w - L - R, H = height - T - B;
  const pts = series.points.filter((p) => p.y != null) as { x: number; y: number; flag?: boolean }[];
  const xMax = Math.max(xMin, ...series.points.map((p) => p.x), 1);
  const X = (x: number) => L + (x / xMax) * W;
  const Y = (y: number) => T + H - (Math.min(Math.max(y, 0), yMax) / yMax) * H;
  const path = pts.map((p, i) => `${i ? "L" : "M"}${X(p.x).toFixed(1)},${Y(p.y).toFixed(1)}`).join(" ");
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * yMax);
  const last = pts.at(-1);

  return (
    <div ref={ref} className="graph-paper relative w-full border-[1.5px] border-ink">
      <svg width={w} height={height} className="block overflow-visible font-mono">
        {target != null && (
          <rect
            x={L}
            width={W}
            y={goodBelow ? Y(target) : T}
            height={goodBelow ? T + H - Y(target) : Y(target) - T}
            fill="rgb(18 122 74 / 0.08)"
          />
        )}
        <line x1={L} x2={L} y1={T} y2={T + H} stroke="var(--color-ink)" strokeWidth={1.5} />
        <line x1={L} x2={L + W} y1={T + H} y2={T + H} stroke="var(--color-ink)" strokeWidth={1.5} />
        {ticks.map((v) => (
          <g key={v}>
            <line x1={L - 4} x2={L} y1={Y(v)} y2={Y(v)} stroke="var(--color-ink)" />
            <text x={L - 7} y={Y(v) + 3} textAnchor="end" fontSize={10} fill="var(--color-ink-2)">
              {Number.isInteger(v) ? v : v.toFixed(yMax > 2 ? 1 : 2)}
            </text>
          </g>
        ))}
        <text x={L} y={height - 8} fontSize={10} fill="var(--color-ink-2)">0</text>
        {xLabel && (
          <text x={L + W / 2} y={height - 8} textAnchor="middle" fontSize={10} fill="var(--color-ink-3)">
            {xLabel}
          </text>
        )}
        <text x={L + W} y={height - 8} textAnchor="end" fontSize={10} fill="var(--color-ink-2)">{xMax}</text>
        {target != null && (
          <g>
            <line x1={L} x2={L + W} y1={Y(target)} y2={Y(target)} stroke="var(--color-good)" strokeWidth={1.5} strokeDasharray="6 4" />
            <text x={L + W - 2} y={Y(target) - 5} textAnchor="end" fontSize={10} fill="var(--color-good)">
              goal {goodBelow ? "<" : ">"} {target}
              {unit}
            </text>
          </g>
        )}
        {path && <path d={path} fill="none" stroke={series.color} strokeWidth={2.25} strokeLinejoin="round" strokeLinecap="round" />}
        {pts.map((p, i) =>
          pts.length > 70 ? null : (
            <rect key={i} x={X(p.x) - 2.5} y={Y(p.y) - 2.5} width={5} height={5} fill="var(--color-card)" stroke={series.color} strokeWidth={1.5} />
          ),
        )}
        {pts.filter((p) => p.flag).map((p, i) => (
          <g key={`f${i}`}>
            <ellipse cx={X(p.x)} cy={Y(p.y)} rx={11} ry={9} fill="none" stroke="var(--color-alert)" strokeWidth={2} transform={`rotate(-12 ${X(p.x)} ${Y(p.y)})`} />
            <text x={X(p.x) + 13} y={Y(p.y) - 9} fontSize={10} fontWeight={600} fill="var(--color-alert)">changed!</text>
          </g>
        ))}
        {last && <rect x={X(last.x) - 4} y={Y(last.y) - 4} width={8} height={8} fill={series.color} />}
      </svg>
      {!pts.length && emptyLabel && (
        <div className="absolute inset-0 grid place-items-center">
          <span className="bg-card px-2 font-display text-sm italic text-ink-3">{emptyLabel}</span>
        </div>
      )}
    </div>
  );
}
