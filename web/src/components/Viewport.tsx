"use client";

import clsx from "clsx";
import { Box, Camera, Eye, EyeOff, Hand, Loader2, MousePointerClick, Pause, PlugZap, ZoomIn, ZoomOut } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { isPushing, send, SIM_URL, type SimState } from "@/lib/sim";

const LEARNER_LABEL: Record<string, string> = {
  tabpfn: "TabPFN",
  tabpfn_nn: "TabPFN + neighbours",
  gp: "Gaussian process",
  mlp: "MLP",
  knn: "kNN",
};

export function Viewport({ state, connected }: { state: SimState | null; connected: boolean | null }) {
  const img = useRef<HTMLImageElement>(null);
  const down = useRef<{ x: number; y: number } | null>(null);
  const dragged = useRef(false);
  const acc = useRef({ dx: 0, dy: 0 });
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [dragging, setDragging] = useState(false);
  const [streamKey, setStreamKey] = useState(0);
  const [ripple, setRipple] = useState<{ x: number; y: number; id: number } | null>(null);

  // Reconnect the MJPEG stream when the server comes back.
  const wasConnected = useRef<boolean | null>(null);
  useEffect(() => {
    if (connected && wasConnected.current === false) setStreamKey((k) => k + 1);
    wasConnected.current = connected;
  }, [connected]);

  useEffect(() => {
    const el = img.current;
    if (!el) return;
    // Plain scrolling scrolls the page; Ctrl/⌘ + scroll (or a trackpad pinch, which arrives as ctrl+wheel) zooms.
    const onWheel = (e: WheelEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      e.preventDefault();
      send({ name: "zoom", delta: e.deltaY * (e.ctrlKey && Math.abs(e.deltaY) < 10 ? 8 : 1) });
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
          setRipple({ x: x * 100, y: y * 100, id: Date.now() });
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
  }, [streamKey]);

  const push = isPushing(state);
  const fitMs = state?.fit_s != null ? Math.round(state.fit_s * 1000) : null;
  const status = push ? state?.push_status : state ? `probe ${state.probes}` : "";

  return (
    <div className="group relative mx-auto w-full max-w-[calc((100vh-290px)*1.6)] overflow-hidden rounded-2xl border border-white/10 bg-black shadow-[0_0_80px_-20px_rgba(56,189,248,0.25)]">
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
          dragging ? "cursor-grabbing" : state?.selected ? "cursor-crosshair" : "cursor-grab",
        )}
      />

      {/* scanline + vignette */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_55%,rgba(0,0,0,0.55))]" />

      {ripple && (
        <span
          key={ripple.id}
          className="pointer-events-none absolute h-10 w-10 -translate-x-1/2 -translate-y-1/2 animate-ping rounded-full border-2 border-amber-300"
          style={{ left: `${ripple.x}%`, top: `${ripple.y}%` }}
          onAnimationEnd={() => setRipple(null)}
        />
      )}

      {/* top-left: what's happening */}
      <div className="pointer-events-none absolute left-4 top-4 flex max-w-[70%] flex-col gap-2">
        <div className="hud flex items-center gap-2 text-sm font-medium text-white">
          {push ? <MousePointerClick className="h-4 w-4 text-sky-300" /> : <Hand className="h-4 w-4 text-amber-300" />}
          <span className="truncate">{state?.beat ?? (push ? "Few-shot pushing" : "Mapping by touch")}</span>
        </div>
        {status && <div className="hud self-start text-xs text-zinc-300">{status}</div>}
      </div>

      {/* top-right: the model */}
      {state && (
        <div className="pointer-events-none absolute right-4 top-4 flex flex-col items-end gap-2">
          <div className="hud flex items-center gap-2 text-xs">
            <span className="h-2 w-2 rounded-full bg-sky-400 shadow-[0_0_10px_2px_rgba(56,189,248,0.7)]" />
            <span className="font-semibold text-sky-200">{LEARNER_LABEL[state.learner] ?? state.learner}</span>
            {fitMs != null && <span className="tabular-nums text-zinc-400">· {fitMs} ms / update</span>}
          </div>
          {state.fitting && (
            <div className="hud flex items-center gap-1.5 text-xs text-sky-300">
              <Loader2 className="h-3 w-3 animate-spin" /> updating {push ? "push model" : "map"}
            </div>
          )}
        </div>
      )}

      {/* bottom: hints + camera */}
      <div className="absolute inset-x-4 bottom-4 flex items-end justify-between gap-3">
        <div className="hud pointer-events-none flex items-center gap-2 text-xs text-zinc-300">
          {state?.selected ? (
            <>
              <Box className="h-3.5 w-3.5 text-amber-300" />
              <span>
                <b className="text-amber-200">{state.selected.replace("_", " ")}</b> selected — click the table to move it
              </span>
            </>
          ) : (
            <span>drag to orbit · ⌘/Ctrl + scroll to zoom · click a box, the puck or the goal, then the table, to move it</span>
          )}
        </div>
        <div className="flex gap-1 rounded-xl border border-white/10 bg-black/50 p-1 backdrop-blur">
          <button onClick={() => send({ name: "zoom", delta: -250 })} title="Zoom in" className="rounded-lg px-2 py-1 text-zinc-300 transition hover:bg-white/10 hover:text-white">
            <ZoomIn className="h-3.5 w-3.5" />
          </button>
          <button onClick={() => send({ name: "zoom", delta: 250 })} title="Zoom out" className="rounded-lg px-2 py-1 text-zinc-300 transition hover:bg-white/10 hover:text-white">
            <ZoomOut className="h-3.5 w-3.5" />
          </button>
          <span className="my-1 w-px bg-white/10" />
          {(["front", "top", "side"] as const).map((v) => (
            <button
              key={v}
              onClick={() => send({ name: "view", value: v })}
              className="flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs capitalize text-zinc-300 transition hover:bg-white/10 hover:text-white"
              title={`${v} view`}
            >
              {v === "front" && <Camera className="h-3 w-3" />}
              {v}
            </button>
          ))}
          <button
            onClick={() => send({ name: "truth" })}
            title="Ground truth overlay (T)"
            className={clsx(
              "flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs transition",
              state?.truth ? "bg-emerald-400/20 text-emerald-300" : "text-zinc-300 hover:bg-white/10 hover:text-white",
            )}
          >
            {state?.truth ? <Eye className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />} truth
          </button>
        </div>
      </div>

      {state && !state.auto && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-black/30 backdrop-blur-[1px]">
          <div className="flex items-center gap-2 rounded-full border border-white/15 bg-black/60 px-4 py-2 text-sm text-white">
            <Pause className="h-4 w-4" /> paused — press Space
          </div>
        </div>
      )}

      {connected === false && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-zinc-950/90 text-center">
          <PlugZap className="h-8 w-8 text-amber-300" />
          <div className="text-lg font-semibold text-white">Simulation server not reachable</div>
          <div className="max-w-md text-sm text-zinc-400">Start it from the project root, then this page reconnects on its own:</div>
          <code className="rounded-lg border border-white/10 bg-black px-3 py-2 font-mono text-xs text-amber-200">
            .venv/bin/python -m src.web.server --mode script --learner tabpfn
          </code>
          <div className="text-xs text-zinc-500">expecting it at {SIM_URL}</div>
        </div>
      )}
    </div>
  );
}
