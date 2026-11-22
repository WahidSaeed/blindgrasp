"use client";

import clsx from "clsx";
import { CircleHelp, FlaskConical, Hand, Layers, Move, Pause, Play, RotateCcw, ScanEye, Snowflake, Target, Weight } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { LineChart } from "@/components/LineChart";
import { InfoTip, Toasts, useStoredFlag, useToasts } from "@/components/ui";
import { LEARNER_LABEL, Viewport } from "@/components/Viewport";
import { narrate, type Tone } from "@/lib/narrate";
import { isPushing, send, SIM_URL, useSimState, type Mode, type SimState } from "@/lib/sim";

const EXPERIMENTS: { mode: Mode; id: string; title: string; blurb: string; icon: typeof Hand }[] = [
  { mode: "map", id: "EXP-01", title: "Feel the table", blurb: "Touch spots to learn where the boxes are", icon: Hand },
  { mode: "push", id: "EXP-02", title: "Learn to push", blurb: "Learn how the puck slides from a few tries", icon: Target },
  { mode: "combined", id: "EXP-03", title: "Feel, then push", blurb: "Map first, then push around what it felt", icon: Layers },
  { mode: "script", id: "DEMO", title: "Guided demo", blurb: "The whole story, with scripted surprises", icon: FlaskConical },
];

const PROTOCOL = [
  ["Feel the table", "The arm touches the table until its map is good enough."],
  ["Someone moves a box", "A box is put on the puck's route. The robot isn't told."],
  ["Push around it", "It checks the route by touch, finds the box, and plans around it."],
  ["The table turns icy", "The puck slides further than predicted; it notices and relearns."],
  ["Done", "Both goals reached."],
];

const SPEEDS = [0.5, 1, 2, 3, 4, 6, 8];

type ActName = "auto" | "reset" | "truth" | "friction" | "mass";

export function Dashboard() {
  const { state, connected } = useSimState();
  const [seenIntro, setSeenIntro] = useStoredFlag("bg-intro-seen-v2");
  const [help, setHelp] = useState(false);
  const [armed, setArmed] = useState(false);
  const [toasts, toast] = useToasts();
  const push = isPushing(state);
  const disarm = useCallback(() => setArmed(false), []);

  const act = useCallback(
    (name: ActName) => {
      send({ name });
      if (!state) return;
      if (name === "reset") toast({ title: "Run reset", body: "The robot forgets everything it has learned and starts blind again." });
      if (name === "friction") {
        const next = state.friction === "normal" ? "icy" : state.friction === "low" ? "sticky" : "normal";
        toast({ title: `Table friction → ${next}`, body: "The robot isn't told. Watch the next push: a big prediction miss is how it notices." });
      }
      if (name === "truth") toast({ title: state.truth ? "Ground truth hidden" : "Ground truth shown", body: state.truth ? undefined : "Outlines show the real objects, for comparing against the robot's map." });
      if (name === "mass") toast({ title: "Puck mass changed", body: "This barely matters: the arm moves at a set speed, so a heavier puck slides about as far." });
    },
    [state, toast],
  );

  const setMode = useCallback(
    (m: Mode) => {
      send({ name: "mode", value: m });
      const e = EXPERIMENTS.find((x) => x.mode === m)!;
      toast({ title: `Loaded ${e.id}: ${e.title}`, body: e.blurb + "." });
    },
    [toast],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (["SELECT", "INPUT", "TEXTAREA"].includes(t.tagName)) return;
      if (e.key === "?") return setHelp((h) => !h);
      if (e.key === "Escape") {
        setHelp(false);
        setArmed(false);
        return;
      }
      const map: Record<string, ActName> = { " ": "auto", r: "reset", t: "truth", f: "friction", m: "mass" };
      const a = map[e.key.toLowerCase()];
      if (a) {
        e.preventDefault();
        act(a);
      }
      if (e.key.toLowerCase() === "g") setArmed((x) => !x);
      const n = Number(e.key);
      if (n >= 1 && n <= 4) setMode(EXPERIMENTS[n - 1].mode);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [act, setMode]);

  const exp = EXPERIMENTS.find((x) => x.mode === state?.mode);

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-bench max-lg:h-auto max-lg:overflow-visible">
      <TopBar state={state} connected={connected} exp={exp} act={act} onHelp={() => setHelp(true)} onAbout={() => setSeenIntro(false)} />

      <div className="grid min-h-0 flex-1 gap-px bg-line lg:grid-cols-[236px_minmax(0,1fr)_300px]">
        <Sidebar state={state} push={push} armed={armed} onArm={() => setArmed((a) => !a)} act={act} setMode={setMode} />

        <div className="grid min-h-0 gap-px bg-line lg:grid-rows-[minmax(0,1fr)_210px]">
          <Viewport state={state} connected={connected} armed={armed} onClicked={disarm} commentary={<Commentary state={state} connected={connected} />} />
          <div className="grid min-h-0 gap-px bg-line md:grid-cols-[1fr_1fr_1.15fr] max-lg:[&>*]:h-[220px]">
            <Scopes state={state} push={push} />
            <Console events={state?.events ?? []} error={state?.error ?? null} />
          </div>
        </div>

        <Inspector state={state} push={push} />
      </div>

      <StatusBar state={state} connected={connected} />

      {seenIntro === false && <Intro onClose={() => setSeenIntro(true)} />}
      {help && <Shortcuts onClose={() => setHelp(false)} />}
      <Toasts toasts={toasts} />
    </div>
  );
}

/* ───────────── top bar ───────────── */

function TopBar({ state, connected, exp, act, onHelp, onAbout }: { state: SimState | null; connected: boolean | null; exp?: (typeof EXPERIMENTS)[number]; act: (n: ActName) => void; onHelp: () => void; onAbout: () => void }) {
  const paused = state?.auto === false;
  return (
    <header className="flex h-11 shrink-0 items-center gap-3 border-b border-line bg-panel px-3">
      <div className="flex items-center gap-2.5">
        <div className="grid h-6 w-6 grid-cols-2 gap-[3px] rounded-[3px] border border-line-2 bg-well p-[4px]" aria-hidden>
          <span className="rounded-full bg-touch" />
          <span className="rounded-full bg-fg-3" />
          <span className="rounded-full bg-fg-3" />
          <span className="rounded-full bg-model" />
        </div>
        <span className="font-mono text-[13px] font-semibold tracking-[0.18em] text-fg">BLINDGRASP</span>
        <span className="font-mono text-[11px] text-fg-3">workstation</span>
      </div>
      <span className="h-5 w-px bg-line-2" />
      <div className="flex min-w-0 items-center gap-2 font-mono text-[11px]">
        <span className="text-fg-3">experiment</span>
        <span className="truncate text-fg">{exp ? `${exp.id} · ${exp.title}` : "—"}</span>
      </div>

      <div className="ml-auto flex items-center gap-1.5">
        <button onClick={() => act("auto")} className={clsx("tool w-[92px] justify-center", paused ? "tool-on" : "")} title="Space">
          {paused ? <Play className="h-3.5 w-3.5" /> : <Pause className="h-3.5 w-3.5" />}
          {paused ? "Run" : "Pause"}
        </button>
        <button onClick={() => act("reset")} className="tool" title="R">
          <RotateCcw className="h-3.5 w-3.5" /> Reset
        </button>
        <label className="ml-1 flex items-center gap-1.5 font-mono text-[11px] text-fg-3">
          speed
          <select value={state?.speed ?? 2} onChange={(e) => send({ name: "speed", value: Number(e.target.value) })} className="field !w-[68px]">
            {SPEEDS.concat(state && !SPEEDS.includes(state.speed) ? [state.speed] : []).map((s) => (
              <option key={s} value={s}>{s}×</option>
            ))}
          </select>
        </label>
        <span className="mx-1 h-5 w-px bg-line-2" />
        <span className={clsx("flex items-center gap-1.5 rounded-[3px] border px-2 py-1 font-mono text-[10.5px]", connected ? "border-ok/40 text-ok" : connected === false ? "border-warn/40 text-warn" : "border-line-2 text-fg-3")}>
          <span className={clsx("h-1.5 w-1.5 rounded-full", connected ? "bg-ok" : connected === false ? "bg-warn" : "bg-fg-3")} />
          {connected ? "connected" : connected === false ? "offline" : "connecting"}
        </span>
        <button onClick={onAbout} className="tool">About</button>
        <button onClick={onHelp} className="tool !px-1.5" title="Shortcuts (?)"><CircleHelp className="h-3.5 w-3.5" /></button>
      </div>
    </header>
  );
}

/* ───────────── left: sidebar ───────────── */

function Sidebar({ state, push, armed, onArm, act, setMode }: { state: SimState | null; push: boolean; armed: boolean; onArm: () => void; act: (n: ActName) => void; setMode: (m: Mode) => void }) {
  const fr = state?.friction ?? "normal";
  return (
    <aside className="panel overflow-x-hidden overflow-y-auto pb-4">
      <div className="section-title !pt-3">Experiments</div>
      <nav className="flex flex-col px-1.5">
        {EXPERIMENTS.map((e, i) => {
          const on = state?.mode === e.mode;
          const Icon = e.icon;
          return (
            <button
              key={e.mode}
              onClick={() => setMode(e.mode)}
              className={clsx("group relative flex gap-2.5 rounded-[3px] px-2 py-2 text-left transition-colors", on ? "bg-model/10" : "hover:bg-panel-2")}
            >
              {on && <span className="absolute inset-y-1 left-0 w-0.5 rounded bg-model" />}
              <Icon className={clsx("mt-0.5 h-4 w-4 shrink-0", on ? "text-model" : "text-fg-3 group-hover:text-fg-2")} />
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2">
                  <span className={clsx("text-[13px] font-medium", on ? "text-fg" : "text-fg-2 group-hover:text-fg")}>{e.title}</span>
                  <span className="kbd ml-auto">{i + 1}</span>
                </span>
                <span className="block font-mono text-[10px] text-fg-3">{e.id}</span>
                <span className="mt-0.5 block text-[11.5px] leading-snug text-fg-3">{e.blurb}</span>
              </span>
            </button>
          );
        })}
      </nav>

      <div className="section-title">
        Interventions
        <InfoTip text="Change the world behind the robot's back. It is never told; it has to notice from what it touches and how the puck moves." align="right" />
      </div>
      <div className="flex flex-col gap-1.5 px-3">
        <button onClick={onArm} className={clsx("tool justify-start", armed && "tool-touch")}>
          <Move className="h-3.5 w-3.5" />
          <span className="flex-1 text-left">{armed ? "Click an object in the view…" : "Move an object"}</span>
          <span className="kbd">G</span>
        </button>
        <button onClick={() => act("friction")} className={clsx("tool justify-start", fr === "low" && "tool-on")}>
          <Snowflake className="h-3.5 w-3.5" />
          <span className="flex-1 text-left">Table friction</span>
          <span className="font-mono text-[10.5px] text-fg-2">{fr === "low" ? "icy" : fr === "high" ? "sticky" : "normal"}</span>
          <span className="kbd">F</span>
        </button>
        <button onClick={() => act("mass")} className="tool justify-start">
          <Weight className="h-3.5 w-3.5" />
          <span className="flex-1 text-left">Puck mass</span>
          <span className="font-mono text-[10.5px] text-fg-2">{state?.mass ?? "normal"}</span>
          <span className="kbd">M</span>
        </button>
        <button onClick={() => act("truth")} className={clsx("tool justify-start", state?.truth && "tool-on")}>
          <ScanEye className="h-3.5 w-3.5" />
          <span className="flex-1 text-left">Ground truth overlay</span>
          <span className="kbd">T</span>
        </button>
      </div>

      <div className="section-title">Parameters</div>
      <div className="flex flex-col gap-3 px-3">
        <Param label="Learner" tip="TabPFN learns from the examples in one pass, with no training. The others are classic baselines to compare against.">
          <select value={state?.learner ?? "tabpfn"} onChange={(e) => send({ name: "learner", value: e.target.value })} className="field">
            {Object.entries(LEARNER_LABEL).map(([v, l]) => (
              <option key={v} value={v}>{l}</option>
            ))}
          </select>
        </Param>
        {push ? (
          <Param label="On physics change" tip="Forget: drop all old pushes once a change is detected. Recent: keep only the latest few. Keep all: never forget (slow to adapt).">
            <Seg value={state?.adapt ?? "reset"} onChange={(v) => send({ name: "adapt", value: v })} options={[["reset", "Forget"], ["window", "Recent"], ["none", "Keep all"]]} />
          </Param>
        ) : (
          <Param label="Probe strategy" tip="Unsure: touch where the model is least certain. Edges: trace box borders. Random and Raster are baselines.">
            <Seg value={state?.strategy ?? "active"} onChange={(v) => send({ name: "strategy", value: v })} options={[["active", "Unsure"], ["lse", "Edges"], ["random", "Random"], ["raster", "Raster"]]} />
          </Param>
        )}
      </div>
    </aside>
  );
}

function Param({ label, tip, children }: { label: string; tip?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="flex items-center gap-1.5 font-mono text-[10.5px] text-fg-2">
        {label}
        {tip && <InfoTip text={tip} align="left" />}
      </span>
      {children}
    </div>
  );
}

function Seg({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: [string, string][] }) {
  return (
    <div className="flex h-7 rounded-[3px] border border-line-2 bg-well p-0.5">
      {options.map(([v, l]) => (
        <button key={v} type="button" onClick={() => onChange(v)} className={clsx("flex-1 rounded-[2px] font-mono text-[10.5px] transition-colors", value === v ? "bg-line-2 text-fg" : "text-fg-3 hover:text-fg-2")}>
          {l}
        </button>
      ))}
    </div>
  );
}

/* ───────────── commentary (inside the viewport panel) ───────────── */

const TONE: Record<Tone, { c: string; tag: string }> = {
  info: { c: "text-fg-2 border-fg-3", tag: "STATUS" },
  think: { c: "text-model border-model", tag: "WORKING" },
  good: { c: "text-ok border-ok", tag: "OK" },
  alert: { c: "text-touch border-touch", tag: "EVENT" },
};

function Commentary({ state, connected }: { state: SimState | null; connected: boolean | null }) {
  const n = narrate(state, connected);
  const t = TONE[n.tone];
  return (
    <div className="flex shrink-0 items-start gap-3 border-b border-line bg-panel px-3 py-2.5" aria-live="polite">
      <span className={clsx("mt-0.5 shrink-0 rounded-[2px] border px-1.5 py-px font-mono text-[10px] font-semibold", t.c)}>{t.tag}</span>
      <div key={n.title} className="min-w-0 animate-[fadein_0.25s_ease-out]">
        <span className="text-[14px] font-semibold text-fg">{n.title}</span>
        <span className="ml-2 text-[13px] text-fg-2">{n.body}</span>
      </div>
    </div>
  );
}

/* ───────────── right: inspector ───────────── */

function Inspector({ state, push }: { state: SimState | null; push: boolean }) {
  return (
    <aside className="panel overflow-x-hidden overflow-y-auto">
      <div className="panel-head">Inspector</div>
      <Readouts state={state} push={push} />
      {state?.mode === "script" ? <Protocol beat={state.beat} /> : <HowToRead push={push} />}
      <Legend push={push} />
    </aside>
  );
}

function Readouts({ state, push }: { state: SimState | null; push: boolean }) {
  const lc = state?.curve?.at(-1);
  const lp = state?.pushes?.at(-1);
  const ms = state?.fit_s != null ? Math.round(state.fit_s * 1000) : null;
  type R = { k: string; v: string; u?: string; sub: string; tip: string; tone?: "ok" | "warn" };
  const think: R = { k: "Update time", v: ms == null ? "—" : ms < 1000 ? String(ms) : (ms / 1000).toFixed(1), u: ms != null && ms >= 1000 ? "s" : "ms", sub: "fit + predict", tip: "How long TabPFN takes to take in every example and predict again. There is no training step." };
  const rows: R[] = push
    ? [
        { k: "Pushes", v: String(state?.pushes.length ?? 0), sub: `${state?.push_rows ?? 0} in memory`, tip: "Each push becomes one example the model learns from. After a physics change the old ones are dropped." },
        { k: "Puck → goal", v: lp ? lp.goal_cm.toFixed(1) : "—", u: "cm", sub: "target < 3 cm", tip: "Where the puck stopped, measured from the centre of the green goal.", tone: lp ? (lp.goal_cm < 3 ? "ok" : undefined) : undefined },
        { k: "Prediction miss", v: lp?.miss_cm != null ? lp.miss_cm.toFixed(1) : "—", u: "cm", sub: lp?.change ? "physics changed" : "predicted vs actual", tip: "Before each push the robot predicts where the puck will stop. This is how far off it was. A sudden big miss means the world changed.", tone: lp?.change ? "warn" : undefined },
        think,
      ]
    : [
        { k: "Touches", v: String(state?.probes ?? 0), sub: `${state?.rows ?? 0} in memory`, tip: "Each touch records one position and the height felt there. These are the only examples the model gets." },
        { k: "Map error", v: lc ? lc.mae_cm.toFixed(2) : "—", u: "cm", sub: "target < 1 cm", tip: "Average difference between the robot's height map and the real table.", tone: lc ? (lc.mae_cm < 1 ? "ok" : undefined) : undefined },
        { k: "Shapes found", v: lc ? String(Math.round(lc.iou * 100)) : "—", u: "%", sub: "overlap with real boxes", tip: "How well the boxes it believes in overlap the real ones (100% = perfect outlines). Edges are hard to feel with a round probe tip." },
        think,
      ];
  return (
    <div className="grid grid-cols-2 gap-px border-b border-line bg-line">
      {rows.map((r, i) => (
        <div key={r.k} className="bg-panel px-3 py-2.5">
          <div className="flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.1em] text-fg-3">
            {r.k}
            <InfoTip text={r.tip} align={i % 2 ? "right" : "left"} />
          </div>
          <div className={clsx("mt-1 font-mono text-[22px] font-medium leading-none tabular-nums", r.tone === "ok" ? "text-ok" : r.tone === "warn" ? "text-warn" : "text-fg")}>
            {r.v}
            {r.u && <span className="ml-1 text-[11px] text-fg-3">{r.u}</span>}
          </div>
          <div className={clsx("mt-1 text-[10.5px]", r.tone === "warn" ? "text-warn" : "text-fg-3")}>{r.sub}</div>
        </div>
      ))}
    </div>
  );
}

function Protocol({ beat }: { beat: string | null }) {
  const cur = beat ? Number(beat.trim()[0]) || 1 : 1;
  return (
    <div className="border-b border-line pb-3">
      <div className="section-title">Protocol · guided demo</div>
      <ol className="flex flex-col px-3">
        {PROTOCOL.map(([h, p], i) => {
          const k = i + 1, done = k < cur || cur === 5, on = k === cur && cur !== 5;
          return (
            <li key={h} className="relative flex gap-2.5 pb-2.5 last:pb-0">
              {i < PROTOCOL.length - 1 && <span className={clsx("absolute left-[7px] top-4 bottom-0 w-px", done ? "bg-ok/50" : "bg-line-2")} />}
              <span
                className={clsx(
                  "relative mt-0.5 grid h-[15px] w-[15px] shrink-0 place-items-center rounded-[3px] border font-mono text-[9px]",
                  done ? "border-ok bg-ok/20 text-ok" : on ? "border-model bg-model/20 text-model" : "border-line-2 bg-panel text-fg-3",
                )}
              >
                {done ? "✓" : k}
              </span>
              <span className="min-w-0">
                <span className={clsx("block text-[12.5px]", on ? "font-medium text-fg" : done ? "text-fg-2" : "text-fg-3")}>
                  {h}
                  {on && <span className="ml-2 font-mono text-[10px] text-model">running</span>}
                </span>
                {on && <span className="block text-[11.5px] leading-snug text-fg-2">{p}</span>}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function HowToRead({ push }: { push: boolean }) {
  const steps = push
    ? ["It makes 3 gentle test pushes to get started.", "Then it predicts where each candidate push sends the puck and picks the best.", "After each push it checks: was the guess right? A big miss means the physics changed."]
    : ["It touches one spot and records the height.", "TabPFN redraws the whole map from all touches so far, with how sure it is.", "It touches next wherever it is least sure. Faded tiles = unsure."];
  return (
    <div className="border-b border-line pb-3">
      <div className="section-title">What it does</div>
      <ol className="flex flex-col gap-1.5 px-3">
        {steps.map((s, i) => (
          <li key={i} className="flex gap-2 text-[12px] leading-snug text-fg-2">
            <span className="font-mono text-[10.5px] text-fg-3">{i + 1}.</span>
            {s}
          </li>
        ))}
      </ol>
    </div>
  );
}

function Legend({ push }: { push: boolean }) {
  const items: [React.ReactNode, string][] = [
    [<span key="g" className="h-2.5 w-9 rounded-[2px]" style={{ background: "linear-gradient(90deg,#2659d9,#f2d933,#e6331f)" }} />, "Map tile: flat → tall"],
    [<span key="f" className="h-2.5 w-2.5 rounded-[2px] bg-[#2659d9]/30" />, "Faded tile: model unsure"],
    [<span key="o" className="h-2.5 w-2.5 rounded-full bg-[#ff8c1a]" />, "Touch hit an object"],
    [<span key="s" className="h-2.5 w-2.5 rounded-full bg-[#8c8c8c]" />, "Touch felt bare table"],
  ];
  if (push) items.push([<span key="p" className="h-2.5 w-2.5 rounded-full bg-[#1ae64d]" />, "Goal / planned push (red = blocked)"]);
  return (
    <div className="pb-3">
      <div className="section-title">Legend</div>
      <ul className="flex flex-col gap-1.5 px-3">
        {items.map(([sw, l]) => (
          <li key={l} className="flex items-center gap-2.5 text-[12px] text-fg-2">
            <span className="flex w-9 justify-center">{sw}</span>
            {l}
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ───────────── bottom dock: scopes + console ───────────── */

function Scopes({ state, push }: { state: SimState | null; push: boolean }) {
  const pushes = useMemo(() => state?.pushes ?? [], [state?.pushes]);
  const curve = useMemo(() => state?.curve ?? [], [state?.curve]);
  const a = push
    ? { id: "CH1", title: "Puck → goal", unit: "cm", color: "var(--color-model)", chart: <LineChart series={{ color: "var(--color-model)", points: pushes.map((p) => ({ x: p.n, y: p.goal_cm, flag: p.change })) }} target={3} unit=" cm" yMax={40} xMin={10} xLabel="push" emptyLabel="waiting for the first push" /> }
    : { id: "CH1", title: "Map error", unit: "cm", color: "var(--color-model)", chart: <LineChart series={{ color: "var(--color-model)", points: curve.map((p) => ({ x: p.n, y: p.mae_cm })) }} target={1} unit=" cm" yMax={4} xLabel="touches" emptyLabel="waiting for touches" /> };
  const b = push
    ? { id: "CH2", title: "Prediction miss", unit: "cm", color: "var(--color-touch)", chart: <LineChart series={{ color: "var(--color-touch)", points: pushes.map((p) => ({ x: p.n, y: p.miss_cm, flag: p.change })) }} target={1.5} unit=" cm" yMax={12} xMin={10} xLabel="push" emptyLabel="predictions start after 3 test pushes" /> }
    : { id: "CH2", title: "Shapes found", unit: "0–1", color: "var(--color-touch)", chart: <LineChart series={{ color: "var(--color-touch)", points: curve.map((p) => ({ x: p.n, y: p.iou })) }} goodBelow={false} yMax={1} xLabel="touches" emptyLabel="waiting for touches" /> };
  return (
    <>
      {[a, b].map((s) => (
        <section key={s.id} className="panel">
          <div className="panel-head">
            <span className="h-2 w-2 rounded-full" style={{ background: s.color }} />
            <span className="text-fg">{s.id}</span>
            <span className="normal-case tracking-normal text-fg-2">{s.title}</span>
            <span className="ml-auto normal-case tracking-normal text-fg-3">{s.unit}</span>
          </div>
          <div className="min-h-0 flex-1 p-2">{s.chart}</div>
        </section>
      ))}
    </>
  );
}

const TAGS: [RegExp, string, string][] = [
  [/PRESENTER/, "DEMO", "text-[#b48cff]"],
  [/physics changed|missed (its )?prediction|CHANGE CONFIRMED|dropped|surprise/, "CHNG", "text-warn"],
  [/route check/, "ROUTE", "text-touch"],
  [/map done|reached|finished/, "OK", "text-ok"],
];

function Console({ events, error }: { events: string[]; error: string | null }) {
  return (
    <section className="panel">
      <div className="panel-head">
        <span className="text-fg">Console</span>
        <span className="normal-case tracking-normal text-fg-3">event log · newest first</span>
        <span className="ml-auto normal-case tracking-normal text-fg-3">{events.length}</span>
      </div>
      <ol className="min-h-0 flex-1 overflow-y-auto bg-well py-1 font-mono text-[11px] leading-[18px]">
        {events.length === 0 && <li className="px-3 text-fg-3">— no events yet —</li>}
        {events.slice().reverse().map((e, i) => {
          const m = e.match(/^\[\s*([\d.]+)s\]\s*(.*)$/);
          const time = m?.[1], text = m?.[2] ?? e;
          const tag = TAGS.find(([re]) => re.test(text));
          return (
            <li key={`${events.length - i}-${e}`} className={clsx("flex gap-2 px-3 hover:bg-panel", i === 0 && "animate-[fadein_0.3s_ease-out]")}>
              <span className="w-12 shrink-0 text-right text-fg-3">{time ? `${Number(time).toFixed(1)}s` : "—"}</span>
              <span className={clsx("w-11 shrink-0", tag ? tag[2] : "text-fg-3")}>{tag ? tag[1] : "INFO"}</span>
              <span className="min-w-0 flex-1 text-fg-2">{text.replace(/^PRESENTER:\s*/, "")}</span>
            </li>
          );
        })}
      </ol>
      {error && <pre className="max-h-20 shrink-0 overflow-auto whitespace-pre-wrap border-t border-warn/40 bg-warn/10 px-3 py-1.5 font-mono text-[10.5px] text-warn">{error}</pre>}
    </section>
  );
}

/* ───────────── status bar ───────────── */

function StatusBar({ state, connected }: { state: SimState | null; connected: boolean | null }) {
  const ms = state?.fit_s != null ? Math.round(state.fit_s * 1000) : null;
  const push = isPushing(state);
  const items = state
    ? [
        `t=${state.t.toFixed(1)}s`,
        `${state.speed}×`,
        `learner=${LEARNER_LABEL[state.learner] ?? state.learner}`,
        `update=${ms ?? "—"}ms`,
        push ? `push_rows=${state.push_rows}` : `map_rows=${state.rows}`,
        `friction=${state.friction}`,
        `mass=${state.mass}`,
      ]
    : [];
  return (
    <footer className="flex h-6 shrink-0 items-center gap-4 overflow-hidden border-t border-line bg-panel-2 px-3 font-mono text-[10.5px] text-fg-3">
      <span className={clsx("flex items-center gap-1.5", connected ? "text-ok" : connected === false ? "text-warn" : "")}>
        <span className={clsx("h-1.5 w-1.5 rounded-full", connected ? "bg-ok" : connected === false ? "bg-warn" : "bg-fg-3")} />
        {SIM_URL.replace(/^https?:\/\//, "")}
      </span>
      {items.map((s) => (
        <span key={s} className="whitespace-nowrap">{s}</span>
      ))}
      {state?.fitting && <span className="text-model">● fitting</span>}
      <span className="ml-auto whitespace-nowrap">drag: orbit · ⌘/ctrl+scroll: zoom · click object → table: move · ? shortcuts</span>
    </footer>
  );
}

/* ───────────── modals ───────────── */

function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: React.ReactNode; wide?: boolean }) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4" onClick={onClose}>
      <div className={clsx("panel max-h-[90vh] w-full overflow-hidden rounded-[4px] border border-line-2 shadow-[0_24px_60px_rgba(0,0,0,0.6)]", wide ? "max-w-2xl" : "max-w-md")} onClick={(e) => e.stopPropagation()}>
        <div className="panel-head">
          <span className="text-fg">{title}</span>
          <button onClick={onClose} className="ml-auto font-mono text-fg-3 hover:text-fg" aria-label="Close">✕</button>
        </div>
        <div className="overflow-y-auto p-5">{children}</div>
      </div>
    </div>
  );
}

function Intro({ onClose }: { onClose: () => void }) {
  const steps = [
    { icon: <Hand className="h-4 w-4 text-touch" />, h: "It's blind", p: "No camera. The arm only knows what it has touched. Each touch gives one height at one spot." },
    { icon: <Layers className="h-4 w-4 text-model" />, h: "It learns from examples, instantly", p: "TabPFN takes every touch or push so far and predicts the rest, with error bars, in about a second. No training." },
    { icon: <Snowflake className="h-4 w-4 text-model" />, h: "You can surprise it", p: "Move a box or make the table icy. The robot isn't told; it notices when the world stops matching its predictions." },
  ];
  return (
    <Modal title="About this workstation" onClose={onClose} wide>
      <h2 className="text-xl font-semibold text-fg">A robot arm that learns its world by touch.</h2>
      <p className="mt-1 text-[13px] text-fg-2">You&apos;re looking at a live MuJoCo simulation of a Franka arm. Here&apos;s the idea in three steps:</p>
      <ol className="mt-4 grid gap-px overflow-hidden rounded-[3px] border border-line bg-line sm:grid-cols-3">
        {steps.map((s, i) => (
          <li key={s.h} className="bg-panel-2 p-3">
            <div className="mb-2 flex items-center gap-2">
              <span className="font-mono text-[10.5px] text-fg-3">0{i + 1}</span>
              {s.icon}
            </div>
            <div className="text-[13px] font-medium text-fg">{s.h}</div>
            <p className="mt-1 text-xs leading-relaxed text-fg-2">{s.p}</p>
          </li>
        ))}
      </ol>
      <div className="mt-4 rounded-[3px] border border-line bg-well p-3 text-xs leading-relaxed text-fg-2">
        <b className="text-fg">Where to look:</b> the status line above the camera explains what&apos;s happening right now. Pick an experiment on the left (start with <b className="text-fg">Guided demo</b>), and try the interventions.
      </div>
      <div className="mt-4 flex justify-end">
        <button onClick={onClose} className="tool tool-on">Open the workstation</button>
      </div>
    </Modal>
  );
}

function Shortcuts({ onClose }: { onClose: () => void }) {
  const rows: [string, string][] = [
    ["Space", "run / pause"],
    ["R", "reset the run"],
    ["1 – 4", "load an experiment"],
    ["G", "move an object (then click it, then click the table)"],
    ["F", "table friction: normal → icy → sticky"],
    ["M", "puck mass"],
    ["T", "ground-truth overlay"],
    ["drag", "orbit the camera"],
    ["⌘/Ctrl + scroll", "zoom"],
    ["Esc", "cancel / close"],
  ];
  return (
    <Modal title="Keyboard & mouse" onClose={onClose}>
      <dl className="grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-2">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt><span className="kbd !h-5 !px-1.5 !text-[10.5px]">{k}</span></dt>
            <dd className="text-[12.5px] text-fg-2">{v}</dd>
          </div>
        ))}
      </dl>
    </Modal>
  );
}
