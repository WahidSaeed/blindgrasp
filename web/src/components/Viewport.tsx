"use client";

import clsx from "clsx";
import { Minus, Pause, Plus } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { isPushing, send, SIM_URL, type SimState } from "@/lib/sim";

export const LEARNER_LABEL: Record<string, string> = {
  tabpfn: "TabPFN",
  tabpfn_nn: "TabPFN + neighbours",
  gp: "Gaussian process",
  mlp: "MLP",
  knn: "Nearest neighbours",
};

interface Props {
  state: SimState | null;
  connected: boolean | null;
  /** set by the "Move something" button: show a big instruction until the user clicks */
  armed: boolean;
  onClicked: () => void;
}

export function Viewport({ state, connected, armed, onClicked }: Props) {
  const img = useRef<HTMLImageElement>(null);
  const down = useRef<{ x: number; y: number } | null>(null);
  const dragged = useRef(false);
  const acc = useRef({ dx: 0, dy: 0 });
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [dragging, setDragging] = useState(false);
  const [streamKey, setStreamKey] = useState(0);
  const [mark, setMark] = useState<{ x: number; y: number; id: number } | null>(null);

  // Reconnect the MJPEG stream when the server comes back.
  const wasConnected = useRef<boolean | null>(null);
  useEffect(() => {
    if (connected && wasConnected.current === false) setStreamKey((k) => k + 1);
    wasConnected.current = connected;
  }, [connected]);

  useEffect(() => {
    const el = img.current;
    if (!el) return;
    // Plain scroll scrolls the page; Ctrl/⌘ + scroll (or a trackpad pinch) zooms.
    const onWheel = (e: WheelEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      e.preventDefault();
      send({ name: "zoom", delta: e.deltaY * (Math.abs(e.deltaY) < 10 ? 8 : 1) });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    const onMove = (e: MouseEvent) => {
      if (!down.current) return;
      const dx = e.clientX - down.current.x, dy = e.clientY - down.current.y;
      if (!dragged.current && Math.hypot(dx, dy) < 4) return;
      dragged.current = true;
      setDragging(true);
      acc.current.dx += dx;
      acc.current.dy += dy;
      down.current = { x: e.clientX, y: e.clientY };
      if (!timer.current)
        timer.current = setTimeout(() => {
          send({ name: "orbit", ...acc.current });
          acc.current = { dx: 0, dy: 0 };
          timer.current = null;
        }, 40);
    };
    const onUp = (e: MouseEvent) => {
      if (!down.current) return;
      setDragging(false);
      if (!dragged.current && img.current) {
        const r = img.current.getBoundingClientRect();
        const x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
        if (x >= 0 && x <= 1 && y >= 0 && y <= 1) {
          send({ name: "click", x, y });
          setMark({ x: x * 100, y: y * 100, id: Date.now() });
          onClicked();
        }
      }
      down.current = null;
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      el.removeEventListener("wheel", onWheel);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [streamKey, onClicked]);

  const push = isPushing(state);
  const fitMs = state?.fit_s != null ? Math.round(state.fit_s * 1000) : null;
  const sel = state?.selected?.replace("_", " ");

  return (
    <figure className="bg-ink p-2 pb-0" style={{ boxShadow: "6px 6px 0 0 rgb(22 19 15 / 0.25)" }}>
      {/* instrument label strip */}
      <figcaption className="flex items-center gap-3 px-1 pb-2 font-mono text-[11px] uppercase tracking-wider text-paper/70">
        <span className="flex items-center gap-1.5 text-paper">
          <span className={clsx("h-2 w-2 rounded-full", connected ? "bg-touch animate-[blink_1.4s_steps(2)_infinite]" : "bg-paper/30")} />
          {connected ? "live" : "no signal"}
        </span>
        <span>fig. 1 — what the camera sees (the robot doesn&apos;t)</span>
        {state && (
          <span className="ml-auto flex items-center gap-3 normal-case tracking-normal">
            <span className="text-paper">{LEARNER_LABEL[state.learner] ?? state.learner}</span>
            {fitMs != null && <span>thinks in {fitMs < 1000 ? `${fitMs} ms` : `${(fitMs / 1000).toFixed(1)} s`}</span>}
            {state.fitting && <span className="text-touch">● updating {push ? "push model" : "map"}</span>}
          </span>
        )}
      </figcaption>

      <div className="relative mx-auto w-full max-w-[calc((100vh-400px)*1.6)]">
        {/* eslint-disable-next-line @next/next/no-img-element -- MJPEG stream, not a static image */}
        <img
          key={streamKey}
          ref={img}
          src={`${SIM_URL}/stream?k=${streamKey}`}
          alt="Live MuJoCo simulation of the Franka arm probing and pushing on the table"
          draggable={false}
          onMouseDown={(e) => {
            down.current = { x: e.clientX, y: e.clientY };
            dragged.current = false;
            e.preventDefault();
          }}
          className={clsx(
            "block aspect-[16/10] w-full select-none object-cover",
            dragging ? "cursor-grabbing" : state?.selected || armed ? "cursor-crosshair" : "cursor-grab",
          )}
        />

        {mark && (
          <span
            key={mark.id}
            className="pointer-events-none absolute h-7 w-7 -translate-x-1/2 -translate-y-1/2 animate-ping border-2 border-touch"
            style={{ left: `${mark.x}%`, top: `${mark.y}%` }}
            onAnimationEnd={() => setMark(null)}
          />
        )}

        {(armed || sel) && (
          <div className="pointer-events-none absolute inset-x-0 top-0 flex justify-center p-3">
            <div className="border-[1.5px] border-ink bg-touch px-3 py-1.5 font-mono text-xs font-medium text-ink">
              {sel ? <>{sel} picked up — now click where it should go on the table</> : <>click a box, the red puck or the green goal…</>}
            </div>
          </div>
        )}

        {/* camera controls */}
        <div className="absolute bottom-3 right-3 flex border-[1.5px] border-ink bg-card font-mono text-[11px]">
          <button onClick={() => send({ name: "zoom", delta: -250 })} title="Zoom in" className="grid w-8 place-items-center border-r border-ink py-1.5 hover:bg-paper-2">
            <Plus className="h-3.5 w-3.5" />
          </button>
          <button onClick={() => send({ name: "zoom", delta: 250 })} title="Zoom out" className="grid w-8 place-items-center border-r border-ink py-1.5 hover:bg-paper-2">
            <Minus className="h-3.5 w-3.5" />
          </button>
          {(["front", "top", "side"] as const).map((v) => (
            <button key={v} onClick={() => send({ name: "view", value: v })} className="border-r border-ink px-2.5 py-1.5 uppercase last:border-r-0 hover:bg-paper-2">
              {v}
            </button>
          ))}
        </div>

        {state && !state.auto && (
          <div className="pointer-events-none absolute inset-0 grid place-items-center bg-ink/25">
            <div className="flex items-center gap-2 border-[1.5px] border-ink bg-card px-4 py-2 font-mono text-sm">
              <Pause className="h-4 w-4" /> PAUSED — press space
            </div>
          </div>
        )}

        {connected === false && (
          <div className="hatch absolute inset-0 flex flex-col items-center justify-center gap-3 bg-card p-6 text-center">
            <div className="font-display text-2xl italic">No signal from the simulation</div>
            <div className="max-w-md text-sm text-ink-2">Start the sim server from the project folder — this page reconnects by itself:</div>
            <code className="border-[1.5px] border-ink bg-paper px-3 py-2 font-mono text-xs">.venv/bin/python -m src.web.server --mode script --learner tabpfn</code>
            <div className="font-mono text-[11px] text-ink-3">expecting it at {SIM_URL}</div>
          </div>
        )}
      </div>

      <div className="flex items-center justify-between px-1 py-2 font-mono text-[11px] text-paper/60">
        <span>drag to look around · ⌘/ctrl + scroll to zoom</span>
        <span>click a box, puck or goal, then the table, to move it</span>
      </div>
    </figure>
  );
}
