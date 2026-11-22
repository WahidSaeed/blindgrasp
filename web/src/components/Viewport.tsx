"use client";

import clsx from "clsx";
import { Eye, EyeOff, Minus, Pause, Plus } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { isPushing, send, SIM_URL, type SimState } from "@/lib/sim";

export const LEARNER_LABEL: Record<string, string> = {
  tabpfn: "TabPFN",
  tabpfn_nn: "TabPFN + neighbours",
  gp: "Gaussian process",
  mlp: "MLP ensemble",
  knn: "Nearest neighbours",
};

const ASPECT = 960 / 600; // server renders 960x600

interface Props {
  state: SimState | null;
  connected: boolean | null;
  /** set by "Move an object": show an instruction until the user clicks */
  armed: boolean;
  onClicked: () => void;
  commentary: React.ReactNode;
}

export function Viewport({ state, connected, armed, onClicked, commentary }: Props) {
  const img = useRef<HTMLImageElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const down = useRef<{ x: number; y: number } | null>(null);
  const dragged = useRef(false);
  const acc = useRef({ dx: 0, dy: 0 });
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [dragging, setDragging] = useState(false);
  const [streamKey, setStreamKey] = useState(0);
  const [mark, setMark] = useState<{ x: number; y: number; id: number } | null>(null);

  // Fit the 16:10 stream inside the panel, so click coordinates map 1:1 to the render.
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => {
      const { width: cw, height: ch } = e.contentRect;
      const w = Math.floor(Math.min(cw - 24, (ch - 24) * ASPECT));
      setSize({ w, h: Math.floor(w / ASPECT) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Reconnect the MJPEG stream when the server comes back.
  const wasConnected = useRef<boolean | null>(null);
  useEffect(() => {
    if (connected && wasConnected.current === false) setStreamKey((k) => k + 1);
    wasConnected.current = connected;
  }, [connected]);

  useEffect(() => {
    const el = img.current;
    if (!el) return;
    // Ctrl/⌘ + scroll (or a trackpad pinch) zooms; plain scroll is left alone.
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
  const sel = state?.selected?.replace("_", " ");

  return (
    <section className="panel h-full min-h-0">
      <div className="panel-head">
        <span className="text-fg">Live view</span>
        <span className="text-fg-3">Camera 1</span>
        <div className="ml-auto flex items-center gap-1 normal-case tracking-normal">
          <button onClick={() => send({ name: "zoom", delta: -250 })} title="Zoom in" className="tool !h-7 !px-2"><Plus className="h-3 w-3" /></button>
          <button onClick={() => send({ name: "zoom", delta: 250 })} title="Zoom out" className="tool !h-7 !px-2"><Minus className="h-3 w-3" /></button>
          <span className="mx-1 h-4 w-px bg-line-2" />
          {(["front", "top", "side"] as const).map((v) => (
            <button key={v} onClick={() => send({ name: "view", value: v })} className="tool !h-7 !px-2.5 !text-[12px] capitalize">{v}</button>
          ))}
          <span className="mx-1 h-4 w-px bg-line-2" />
          <button onClick={() => send({ name: "truth" })} title="Overlay the real layout (T)" className={clsx("tool !h-7 !px-2.5 !text-[12px]", state?.truth && "tool-on")}>
            {state?.truth ? <Eye className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />} ground truth
          </button>
        </div>
      </div>

      {commentary}

      <div ref={box} className="bench-grid relative grid min-h-[280px] flex-1 place-items-center overflow-hidden">
        <div className="relative" style={{ width: size.w, height: size.h }}>
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
              "block h-full w-full select-none rounded-lg object-cover ring-1 ring-white/10 shadow-[0_20px_50px_-20px_rgba(0,0,0,0.9)]",
              dragging ? "cursor-grabbing" : state?.selected || armed ? "cursor-crosshair" : "cursor-grab",
            )}
          />

          {/* HUD */}
          <div className="pointer-events-none absolute left-3 top-3 flex items-center gap-2 rounded-full bg-black/45 px-2.5 py-1 text-[11px] font-medium text-fg ring-1 ring-white/10 backdrop-blur-md">
            <span className={clsx("h-1.5 w-1.5 rounded-full", connected ? "bg-warn animate-[blink_1.2s_steps(2)_infinite]" : "bg-fg-3")} />
            {connected ? "LIVE" : "NO SIGNAL"}
            {state && <span className="text-fg-2">· {push ? "PUSH" : "MAP"} · {state.speed}×</span>}
          </div>
          {state?.fitting && (
            <div className="pointer-events-none absolute right-3 top-3 rounded-full bg-black/45 px-2.5 py-1 text-[11px] font-medium text-[#9ad9f5] ring-1 ring-white/10 backdrop-blur-md">
              ◌ updating {push ? "push model" : "map"}…
            </div>
          )}

          {mark && (
            <span
              key={mark.id}
              className="pointer-events-none absolute h-6 w-6 -translate-x-1/2 -translate-y-1/2 animate-ping rounded-full border-2 border-touch"
              style={{ left: `${mark.x}%`, top: `${mark.y}%` }}
              onAnimationEnd={() => setMark(null)}
            />
          )}

          {(armed || sel) && (
            <div className="pointer-events-none absolute inset-x-0 bottom-3 flex justify-center">
              <div className="rounded-full bg-black/60 px-3.5 py-1.5 text-xs font-medium text-[#ffc56b] ring-1 ring-touch/50 backdrop-blur-md">
                {sel ? <>▸ {sel} picked up — click where it should go on the table</> : <>▸ click a box, the red puck or the green goal</>}
              </div>
            </div>
          )}

          {state && !state.auto && (
            <div className="pointer-events-none absolute inset-0 grid place-items-center bg-black/40">
              <div className="flex items-center gap-2 rounded-full bg-black/60 px-4 py-2 text-xs font-medium ring-1 ring-white/15 backdrop-blur-md">
                <Pause className="h-3.5 w-3.5" /> Paused
              </div>
            </div>
          )}
        </div>

        {connected === false && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-well/95 p-6 text-center">
            <div className="font-mono text-sm text-warn">NO SIGNAL · simulation server not reachable</div>
            <div className="max-w-md text-xs text-fg-2">Start it from the project folder; this panel reconnects by itself.</div>
            <code className="rounded-[3px] border border-line-2 bg-panel px-3 py-2 font-mono text-xs text-touch">
              .venv/bin/python -m src.web.server --mode script --learner tabpfn
            </code>
            <div className="font-mono text-[10.5px] text-fg-3">expecting {SIM_URL}</div>
          </div>
        )}

      </div>
    </section>
  );
}
