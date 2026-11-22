"use client";

import clsx from "clsx";
import {
  Activity,
  Brain,
  Gauge,
  Hand,
  Keyboard,
  Layers,
  Pause,
  Play,
  RotateCcw,
  Snowflake,
  Sparkles,
  Target,
  Weight,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { LineChart } from "@/components/LineChart";
import { Viewport } from "@/components/Viewport";
import { isPushing, send, useSimState, type Mode, type SimState } from "@/lib/sim";

const ACTS: { mode: Mode; title: string; kicker: string; blurb: string; icon: typeof Hand }[] = [
  { mode: "map", kicker: "Act 1", title: "Map by touch", blurb: "Probe where the model is least sure", icon: Hand },
  { mode: "push", kicker: "Act 2", title: "Few-shot pushing", blurb: "Every push is a new context row", icon: Target },
  { mode: "combined", kicker: "Acts 1 + 2", title: "Map, then push", blurb: "Route around what it felt", icon: Layers },
  { mode: "script", kicker: "Presenter", title: "Scripted demo", blurb: "Fixed seeds, scripted interrupts", icon: Sparkles },
];

const BEATS = ["Map by touch", "Box moved onto the route", "Push around it", "Table turns icy", "Done"];

const LEARNERS = [
  { v: "tabpfn", label: "TabPFN" },
  { v: "tabpfn_nn", label: "TabPFN + neighbours" },
  { v: "gp", label: "Gaussian process" },
  { v: "mlp", label: "MLP ensemble" },
  { v: "knn", label: "k-nearest neighbours" },
];

export function Dashboard() {
  const { state, connected } = useSimState();
  const [help, setHelp] = useState(false);
  const push = isPushing(state);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t.tagName === "SELECT" || t.tagName === "INPUT") return;
      if (e.key === "?") return setHelp((h) => !h);
      if (e.key === "Escape") return setHelp(false);
      const map: Record<string, "auto" | "reset" | "truth" | "friction" | "mass"> = {
        " ": "auto", r: "reset", t: "truth", f: "friction", m: "mass",
      };
      const a = map[e.key.toLowerCase()];
      if (a) {
        e.preventDefault();
        send({ name: a });
      }
      const n = Number(e.key);
      if (n >= 1 && n <= 4) send({ name: "mode", value: ACTS[n - 1].mode });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="relative min-h-screen overflow-x-hidden">
      <Backdrop />
      <Header state={state} connected={connected} onHelp={() => setHelp(true)} />

      <main className="relative mx-auto grid max-w-[1600px] gap-5 px-5 pb-10 xl:grid-cols-[minmax(0,1fr)_380px]">
        <section className="flex min-w-0 flex-col gap-5">
          <ActSwitcher mode={state?.mode} />
          <Viewport state={state} connected={connected} />
          {state?.mode === "script" ? <BeatTimeline beat={state.beat} /> : state?.mode === "combined" ? <PhaseStrip phase={state.phase} /> : null}
          <div className="grid gap-5 md:grid-cols-2">
            <Charts state={state} push={push} />
          </div>
        </section>

        <aside className="flex flex-col gap-5">
          <Metrics state={state} push={push} />
          <Controls state={state} push={push} />
          <EventLog events={state?.events ?? []} error={state?.error ?? null} />
        </aside>
      </main>

      {help && <Shortcuts onClose={() => setHelp(false)} />}
    </div>
  );
}

function Backdrop() {
  return (
    <div className="pointer-events-none fixed inset-0 -z-10">
      <div className="absolute inset-0 bg-[#06080b]" />
      <div className="absolute -top-40 left-1/4 h-[520px] w-[720px] rounded-full bg-sky-500/10 blur-[140px]" />
      <div className="absolute -bottom-40 right-0 h-[480px] w-[620px] rounded-full bg-amber-500/10 blur-[140px]" />
      <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.025)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.025)_1px,transparent_1px)] bg-[size:48px_48px] [mask-image:radial-gradient(ellipse_at_top,black_30%,transparent_75%)]" />
    </div>
  );
}

function Header({ state, connected, onHelp }: { state: SimState | null; connected: boolean | null; onHelp: () => void }) {
  return (
    <header className="relative mx-auto flex max-w-[1600px] flex-wrap items-center gap-4 px-5 py-5">
      <div className="flex items-center gap-3">
        <div className="relative grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-amber-300 to-sky-400 shadow-lg shadow-sky-500/20">
          <Hand className="h-5 w-5 text-zinc-950" strokeWidth={2.5} />
        </div>
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-white">Blindgrasp</h1>
          <p className="text-xs text-zinc-400">
            A blind robot arm that learns its world by touch — with <span className="text-sky-300">TabPFN</span> in-context learning, no training
          </p>
        </div>
      </div>
      <div className="ml-auto flex items-center gap-2">
        {state && (
          <div className="chip tabular-nums">
            <Activity className="h-3.5 w-3.5 text-zinc-400" /> sim {state.t.toFixed(0)} s · {state.speed}×
          </div>
        )}
        <div className={clsx("chip", connected ? "text-emerald-300" : connected === false ? "text-rose-300" : "text-zinc-400")}>
          <span className="relative flex h-2 w-2">
            {connected && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />}
            <span className={clsx("relative inline-flex h-2 w-2 rounded-full", connected ? "bg-emerald-400" : connected === false ? "bg-rose-400" : "bg-zinc-500")} />
          </span>
          {connected ? "live" : connected === false ? "offline" : "connecting"}
        </div>
        <button onClick={onHelp} className="chip hover:border-white/25 hover:text-white" title="Keyboard shortcuts (?)">
          <Keyboard className="h-3.5 w-3.5" /> ?
        </button>
      </div>
    </header>
  );
}

function ActSwitcher({ mode }: { mode?: Mode }) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {ACTS.map((a, i) => {
        const on = mode === a.mode;
        const Icon = a.icon;
        return (
          <button
            key={a.mode}
            onClick={() => send({ name: "mode", value: a.mode })}
            className={clsx(
              "group relative overflow-hidden rounded-2xl border p-4 text-left transition",
              on ? "border-sky-400/50 bg-sky-400/[0.08] shadow-[0_0_40px_-12px_rgba(56,189,248,0.6)]" : "border-white/10 bg-white/[0.02] hover:border-white/20 hover:bg-white/[0.04]",
            )}
          >
            <div className="flex items-center justify-between">
              <span className={clsx("text-[11px] font-semibold uppercase tracking-[0.14em]", on ? "text-sky-300" : "text-zinc-500")}>{a.kicker}</span>
              <kbd className="kbd">{i + 1}</kbd>
            </div>
            <div className="mt-2 flex items-center gap-2">
              <Icon className={clsx("h-4 w-4", on ? "text-sky-300" : "text-zinc-400")} />
              <span className="font-medium text-white">{a.title}</span>
            </div>
            <p className="mt-1 text-xs text-zinc-400">{a.blurb}</p>
            {on && <span className="absolute inset-x-0 bottom-0 h-0.5 bg-gradient-to-r from-sky-400 via-sky-300 to-amber-300" />}
          </button>
        );
      })}
    </div>
  );
}

function BeatTimeline({ beat }: { beat: string | null }) {
  const cur = beat ? Number(beat.trim()[0]) || 1 : 1;
  return (
    <div className="card p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="label">Presenter script</h2>
        <span className="text-xs text-zinc-400">{beat}</span>
      </div>
      <ol className="grid grid-cols-5 gap-2">
        {BEATS.map((b, i) => {
          const n = i + 1, done = n < cur || (n === 5 && cur === 5), on = n === cur && cur !== 5;
          return (
            <li key={b} className="flex flex-col gap-2">
              <div className="h-1.5 overflow-hidden rounded-full bg-white/5">
                <div className={clsx("h-full rounded-full transition-all duration-700", done ? "w-full bg-emerald-400" : on ? "w-1/2 animate-pulse bg-sky-400" : "w-0")} />
              </div>
              <div className={clsx("text-xs", on ? "text-white" : done ? "text-emerald-300/90" : "text-zinc-500")}>
                <span className="mr-1 tabular-nums opacity-60">{n}</span>
                {b}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function PhaseStrip({ phase }: { phase: string | null }) {
  return (
    <div className="card flex items-center gap-3 p-4 text-sm">
      <span className="label">Phase</span>
      {["MAP", "PUSH"].map((p, i) => (
        <span key={p} className="flex items-center gap-3">
          {i > 0 && <span className="h-px w-8 bg-white/15" />}
          <span className={clsx("rounded-full px-3 py-1 text-xs", phase === p ? "bg-sky-400/15 text-sky-200 ring-1 ring-sky-400/40" : "text-zinc-500")}>
            {p === "MAP" ? "Map by touch" : "Push around the boxes"}
          </span>
        </span>
      ))}
    </div>
  );
}

function Metrics({ state, push }: { state: SimState | null; push: boolean }) {
  const lastCurve = state?.curve?.at(-1);
  const lastPush = state?.pushes?.at(-1);
  const fitMs = state?.fit_s != null ? Math.round(state.fit_s * 1000) : null;
  const cards = push
    ? [
        { k: "pushes", v: state?.pushes.length ?? 0, sub: `${state?.push_rows ?? 0} rows in context`, icon: Target },
        { k: "distance to goal", v: lastPush ? `${lastPush.goal_cm.toFixed(1)} cm` : "–", sub: "target < 3 cm", good: lastPush ? lastPush.goal_cm < 3 : undefined, icon: Target },
        { k: "prediction miss", v: lastPush?.miss_cm != null ? `${lastPush.miss_cm.toFixed(1)} cm` : "–", sub: lastPush?.change ? "physics changed!" : "where it went vs predicted", bad: lastPush?.change, icon: Brain },
        { k: "model update", v: fitMs != null ? `${fitMs} ms` : "–", sub: "fit + predict, no training", good: fitMs != null ? fitMs <= 1000 : undefined, icon: Gauge },
      ]
    : [
        { k: "probes", v: state?.probes ?? 0, sub: `${state?.rows ?? 0} rows in context`, icon: Hand },
        { k: "height error", v: lastCurve ? `${lastCurve.mae_cm.toFixed(2)} cm` : "–", sub: "target < 1 cm", good: lastCurve ? lastCurve.mae_cm < 1 : undefined, icon: Layers },
        { k: "box outline IoU", v: lastCurve ? lastCurve.iou.toFixed(2) : "–", sub: "vs what a probe can feel", icon: Target },
        { k: "map update", v: fitMs != null ? `${fitMs} ms` : "–", sub: "fit + predict, no training", good: fitMs != null ? fitMs <= 1000 : undefined, icon: Gauge },
      ];
  return (
    <div className="grid grid-cols-2 gap-3">
      {cards.map((c) => {
        const Icon = c.icon;
        return (
          <div key={c.k} className="card p-4">
            <div className="flex items-center justify-between">
              <span className="label">{c.k}</span>
              <Icon className="h-3.5 w-3.5 text-zinc-500" />
            </div>
            <div
              className={clsx(
                "mt-2 text-2xl font-semibold tabular-nums tracking-tight transition-colors",
                "bad" in c && c.bad ? "text-rose-400" : "good" in c && c.good === true ? "text-emerald-300" : "text-white",
              )}
            >
              {c.v}
            </div>
            <div className={clsx("mt-1 text-[11px]", "bad" in c && c.bad ? "text-rose-300" : "text-zinc-500")}>{c.sub}</div>
          </div>
        );
      })}
    </div>
  );
}

function Charts({ state, push }: { state: SimState | null; push: boolean }) {
  const pushes = useMemo(() => state?.pushes ?? [], [state?.pushes]);
  const curve = useMemo(() => state?.curve ?? [], [state?.curve]);
  if (push)
    return (
      <>
        <ChartCard title="Distance to goal after each push" note="red = physics change detected">
          <LineChart
            series={{ color: "#38bdf8", points: pushes.map((p) => ({ x: p.n, y: p.goal_cm, flag: p.change })) }}
            target={3}
            unit=" cm"
            yMax={40}
            xMin={10}
            emptyLabel="waiting for the first push"
          />
        </ChartCard>
        <ChartCard title="Prediction miss per push" note="where the puck went vs where TabPFN said">
          <LineChart
            series={{ color: "#fbbf24", points: pushes.map((p) => ({ x: p.n, y: p.miss_cm, flag: p.change })) }}
            target={1.5}
            unit=" cm"
            yMax={12}
            xMin={10}
            emptyLabel="first predictions after 3 seed pushes"
          />
        </ChartCard>
      </>
    );
  return (
    <>
      <ChartCard title="Height error vs probes" note="mean over the table, cm">
        <LineChart
          series={{ color: "#38bdf8", points: curve.map((p) => ({ x: p.n, y: p.mae_cm })) }}
          target={1}
          unit=" cm"
          yMax={4}
          emptyLabel="waiting for the first probes"
        />
      </ChartCard>
      <ChartCard title="Box outline IoU vs probes" note="higher is better">
        <LineChart
          series={{ color: "#fbbf24", points: curve.map((p) => ({ x: p.n, y: p.iou })) }}
          goodBelow={false}
          yMax={1}
          emptyLabel="waiting for the first probes"
        />
      </ChartCard>
    </>
  );
}

function ChartCard({ title, note, children }: { title: string; note: string; children: React.ReactNode }) {
  return (
    <div className="card p-4">
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <h2 className="text-sm font-medium text-white">{title}</h2>
        <span className="truncate text-[11px] text-zinc-500">{note}</span>
      </div>
      {children}
    </div>
  );
}

function Controls({ state, push }: { state: SimState | null; push: boolean }) {
  const [speed, setSpeed] = useState<number | null>(null);
  const shownSpeed = speed ?? state?.speed ?? 2;
  const icy = state?.friction === "low";
  return (
    <div className="card flex flex-col gap-4 p-4">
      <div className="flex items-center justify-between">
        <h2 className="label">Controls</h2>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <button onClick={() => send({ name: "auto" })} className={clsx("btn", state && !state.auto && "btn-primary")}>
          {state?.auto === false ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
          {state?.auto === false ? "Resume" : "Pause"}
          <kbd className="kbd ml-auto">Space</kbd>
        </button>
        <button onClick={() => send({ name: "reset" })} className="btn">
          <RotateCcw className="h-4 w-4" /> Reset <kbd className="kbd ml-auto">R</kbd>
        </button>
      </div>

      <Field label="Learner">
        <select value={state?.learner ?? "tabpfn"} onChange={(e) => send({ name: "learner", value: e.target.value })} className="select">
          {LEARNERS.map((l) => (
            <option key={l.v} value={l.v}>{l.label}</option>
          ))}
        </select>
      </Field>

      {push ? (
        <Field label="When physics changes">
          <Segmented
            value={state?.adapt ?? "reset"}
            onChange={(v) => send({ name: "adapt", value: v })}
            options={[{ v: "reset", label: "Reset" }, { v: "window", label: "Window" }, { v: "none", label: "Never forget" }]}
          />
        </Field>
      ) : (
        <Field label="Where to probe">
          <Segmented
            value={state?.strategy ?? "active"}
            onChange={(v) => send({ name: "strategy", value: v })}
            options={[{ v: "active", label: "Uncertain" }, { v: "lse", label: "Edges" }, { v: "random", label: "Random" }, { v: "raster", label: "Raster" }]}
          />
        </Field>
      )}

      <Field label={`Sim speed · ${shownSpeed}×`}>
        <input
          type="range"
          min={0.5}
          max={8}
          step={0.5}
          value={shownSpeed}
          onChange={(e) => {
            const v = Number(e.target.value);
            setSpeed(v);
            send({ name: "speed", value: v });
          }}
          onMouseUp={() => setSpeed(null)}
          onTouchEnd={() => setSpeed(null)}
          className="range"
        />
      </Field>

      <Field label="Interrupts — the robot isn't told">
        <div className="grid grid-cols-2 gap-2">
          <button onClick={() => send({ name: "friction" })} className={clsx("btn", icy && "border-sky-300/50 bg-sky-300/10 text-sky-100")}>
            <Snowflake className={clsx("h-4 w-4", icy && "text-sky-300")} />
            <span className="truncate">table: {icy ? "icy" : state?.friction ?? "normal"}</span>
            <kbd className="kbd ml-auto">F</kbd>
          </button>
          <button onClick={() => send({ name: "mass" })} className="btn">
            <Weight className="h-4 w-4" />
            <span className="truncate">puck: {state?.mass ?? "normal"}</span>
            <kbd className="kbd ml-auto">M</kbd>
          </button>
        </div>
      </Field>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-zinc-500">{label}</span>
      {children}
    </label>
  );
}

function Segmented({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: { v: string; label: string }[] }) {
  return (
    <div className="flex rounded-xl border border-white/10 bg-black/30 p-1">
      {options.map((o) => (
        <button
          key={o.v}
          type="button"
          onClick={() => onChange(o.v)}
          className={clsx(
            "flex-1 rounded-lg px-2 py-1.5 text-xs transition",
            value === o.v ? "bg-white/10 text-white shadow-inner" : "text-zinc-400 hover:text-white",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

const TAGS: [RegExp, string, string][] = [
  [/PRESENTER/, "presenter", "bg-violet-400/15 text-violet-300"],
  [/physics changed|missed (its )?prediction|change confirmed|dropped/, "change", "bg-rose-400/15 text-rose-300"],
  [/route check/, "route", "bg-amber-400/15 text-amber-300"],
  [/map done|reached|finished/, "milestone", "bg-emerald-400/15 text-emerald-300"],
  [/new run|learner|mode|adaptation/, "system", "bg-white/10 text-zinc-300"],
];

function EventLog({ events, error }: { events: string[]; error: string | null }) {
  return (
    <div className="card flex min-h-0 flex-col p-4">
      <h2 className="label mb-3">Events</h2>
      <ol className="flex max-h-[340px] flex-col gap-2 overflow-y-auto pr-1">
        {events.slice().reverse().map((e, i) => {
          const m = e.match(/^\[\s*([\d.]+)s\]\s*(.*)$/);
          const time = m?.[1], text = m?.[2] ?? e;
          const tag = TAGS.find(([re]) => re.test(text));
          return (
            <li key={`${events.length - i}-${e}`} className={clsx("flex gap-2 text-xs leading-relaxed", i === 0 && "animate-[fadein_0.4s_ease-out]")}>
              <span className="w-12 shrink-0 pt-0.5 text-right font-mono text-[10px] tabular-nums text-zinc-600">{time ? `${Number(time).toFixed(0)}s` : ""}</span>
              <span className="min-w-0 flex-1 text-zinc-300">
                {tag && <span className={clsx("mr-1.5 rounded px-1.5 py-0.5 text-[10px] font-medium", tag[2])}>{tag[1]}</span>}
                {text.replace(/^PRESENTER:\s*/, "")}
              </span>
            </li>
          );
        })}
      </ol>
      {error && <pre className="mt-3 whitespace-pre-wrap rounded-lg bg-rose-500/10 p-2 font-mono text-[11px] text-rose-300">{error}</pre>}
    </div>
  );
}

function Shortcuts({ onClose }: { onClose: () => void }) {
  const rows: [string, string][] = [
    ["Space", "pause / resume"],
    ["R", "reset the run"],
    ["T", "ground-truth overlay"],
    ["F", "cycle table friction (normal → icy → sticky)"],
    ["M", "cycle puck mass"],
    ["1 – 4", "switch act"],
    ["drag / scroll", "orbit / zoom the camera"],
    ["click", "select a box, puck or goal, then click the table to move it"],
  ];
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div className="card w-[420px] p-5" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold text-white">Keyboard & mouse</h2>
          <button onClick={onClose} className="rounded-lg p-1 text-zinc-400 hover:bg-white/10 hover:text-white">
            <X className="h-4 w-4" />
          </button>
        </div>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
          {rows.map(([k, v]) => (
            <div key={k} className="contents">
              <dt><kbd className="kbd">{k}</kbd></dt>
              <dd className="text-zinc-300">{v}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}
