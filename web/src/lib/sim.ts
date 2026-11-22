"use client";

import { useEffect, useRef, useState } from "react";

/** The Python sim server (src/web/server.py). Override with NEXT_PUBLIC_SIM_URL. */
export const SIM_URL = (process.env.NEXT_PUBLIC_SIM_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

export type Mode = "map" | "push" | "combined" | "script";
export type Learner = "tabpfn" | "tabpfn_nn" | "gp" | "mlp" | "knn";

export interface CurvePoint {
  n: number;
  mae_cm: number;
  iou: number;
}

export interface PushPoint {
  n: number;
  goal_cm: number;
  miss_cm: number | null;
  spread_cm: number | null;
  change: boolean;
}

export interface SimState {
  t: number;
  auto: boolean;
  speed: number;
  learner: Learner;
  strategy: string;
  probes: number;
  rows: number;
  fitting: boolean;
  fit_s: number | null;
  friction: string;
  mass: string;
  truth: boolean;
  selected: string | null;
  curve: CurvePoint[];
  events: string[];
  mode: Mode;
  adapt: string;
  pushes: PushPoint[];
  push_status: string;
  phase: "MAP" | "PUSH" | null;
  beat: string | null;
  push_rows: number;
  error: string | null;
}

export type Action =
  | { name: "auto" | "reset" | "truth" | "friction" | "mass" }
  | { name: "speed"; value: number }
  | { name: "learner" | "strategy" | "mode" | "adapt" | "view"; value: string }
  | { name: "orbit"; dx: number; dy: number }
  | { name: "zoom"; delta: number }
  | { name: "click"; x: number; y: number };

export function send(a: Action): void {
  fetch(`${SIM_URL}/action`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(a),
  }).catch(() => {
    /* the status pill shows the disconnect */
  });
}

/** Poll /state. `connected` turns false after a failed poll. */
export function useSimState(intervalMs = 400) {
  const [state, setState] = useState<SimState | null>(null);
  const [connected, setConnected] = useState<boolean | null>(null);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const r = await fetch(`${SIM_URL}/state`, { cache: "no-store" });
        const s = (await r.json()) as SimState;
        if (!alive.current) return;
        setState(s);
        setConnected(true);
      } catch {
        if (alive.current) setConnected(false);
      }
      if (alive.current) timer = setTimeout(tick, intervalMs);
    };
    tick();
    return () => {
      alive.current = false;
      clearTimeout(timer);
    };
  }, [intervalMs]);

  return { state, connected };
}

/** Is the run currently in its pushing half? */
export function isPushing(s: SimState | null): boolean {
  if (!s) return false;
  return s.mode === "push" || ((s.mode === "combined" || s.mode === "script") && s.phase === "PUSH");
}
