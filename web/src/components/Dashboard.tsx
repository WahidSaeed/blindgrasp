"use client";

import clsx from "clsx";
import { ChevronDown, Hand, Move, Pause, Play, RotateCcw, ScanEye, Snowflake } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { LineChart } from "@/components/LineChart";
import { Braille, BrailleRule, InfoTip, Toasts, useStoredFlag, useToasts } from "@/components/ui";
import { LEARNER_LABEL, Viewport } from "@/components/Viewport";
import { narrate, type Tone } from "@/lib/narrate";
import { isPushing, send, useSimState, type Mode, type SimState } from "@/lib/sim";

const ACTS: { mode: Mode; n: string; title: string; blurb: string; dots: number[] }[] = [
  { mode: "map", n: "I", title: "Feel the table", blurb: "It touches spots to learn where the boxes are.", dots: [1] },
  { mode: "push", n: "II", title: "Learn to push", blurb: "It learns how the puck slides from a few tries.", dots: [1, 2] },
  { mode: "combined", n: "III", title: "Feel, then push", blurb: "Maps the table, then pushes around what it felt.", dots: [1, 4] },
  { mode: "script", n: "★", title: "Guided demo", blurb: "The full story with surprises, start to finish.", dots: [1, 4, 5] },
];

const BEATS = ["Feel the table", "Someone moves a box", "Push around it", "The table turns icy", "Done"];

export function Dashboard() {
  const { state, connected } = useSimState();
  const [seenIntro, setSeenIntro] = useStoredFlag("bg-intro-seen");
  const [help, setHelp] = useState(false);
  const [armed, setArmed] = useState(false);
  const [toasts, toast] = useToasts();
  const push = isPushing(state);
  const disarm = useCallback(() => setArmed(false), []);

  const act = useCallback(
    (name: "auto" | "reset" | "truth" | "friction" | "mass") => {
      send({ name });
      if (!state) return;
      if (name === "reset") toast({ title: "Starting over", body: "The robot forgets everything it has learned and begins blind again." });
      if (name === "friction") {
        const next = state.friction === "normal" ? "icy" : state.friction === "low" ? "sticky" : "normal";
        toast({
          title: next === "icy" ? "The table is now icy" : next === "sticky" ? "The table is now sticky" : "Table back to normal",
          body: "The robot isn't told. Watch whether its next push misses — that's how it notices.",
        });
      }
      if (name === "truth") toast({ title: state.truth ? "True layout hidden" : "Showing the true layout", body: state.truth ? undefined : "Outlines show where things really are, so you can compare with the robot's map." });
      if (name === "mass") toast({ title: "Puck weight changed", body: "Fun fact: this barely matters — the arm moves at a set speed, so a heavier puck slides about as far." });
    },
    [state, toast],
  );

  const setMode = useCallback(
    (m: Mode) => {
      send({ name: "mode", value: m });
      const a = ACTS.find((x) => x.mode === m)!;
      toast({ title: a.title, body: a.blurb });
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
      const map: Record<string, "auto" | "reset" | "truth" | "friction" | "mass"> = { " ": "auto", r: "reset", t: "truth", f: "friction", m: "mass" };
      const a = map[e.key.toLowerCase()];
      if (a) {
        e.preventDefault();
        act(a);
      }
      const n = Number(e.key);
      if (n >= 1 && n <= 4) setMode(ACTS[n - 1].mode);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [act, setMode]);

  return (
    <div className="min-h-screen overflow-x-clip">
      <Masthead connected={connected} state={state} onHelp={() => setHelp(true)} onIntro={() => setSeenIntro(false)} />

      <main className="mx-auto grid max-w-[1560px] gap-6 px-6 pb-14 xl:grid-cols-[minmax(0,1fr)_370px]">
        <section className="flex min-w-0 flex-col gap-5">
          <ActTabs mode={state?.mode} onPick={setMode} />
          <Narrator state={state} connected={connected} />
          <Viewport state={state} connected={connected} armed={armed} onClicked={disarm} />
          {state?.mode === "script" && <BeatTimeline beat={state.beat} />}
          <MapKey push={push} />
          <div className="grid gap-5 md:grid-cols-2">
            <Charts state={state} push={push} />
          </div>
        </section>

        <aside className="flex flex-col gap-5">
          <Numbers state={state} push={push} />
          <TryIt state={state} armed={armed} onArm={() => setArmed((a) => !a)} act={act} />
          <Advanced state={state} push={push} act={act} />
          <Notebook events={state?.events ?? []} error={state?.error ?? null} />
        </aside>
      </main>

      {seenIntro === false && <Intro onClose={() => setSeenIntro(true)} />}
      {help && <Shortcuts onClose={() => setHelp(false)} />}
      <Toasts toasts={toasts} />
    </div>
  );
}

/* ───────────────────────── header ───────────────────────── */

function Masthead({ connected, state, onHelp, onIntro }: { connected: boolean | null; state: SimState | null; onHelp: () => void; onIntro: () => void }) {
  return (
    <header className="mx-auto max-w-[1560px] px-6 pt-7 pb-5">
      <div className="flex flex-wrap items-end gap-x-6 gap-y-3 border-b-[1.5px] border-ink pb-4">
        <div>
          <div className="eyebrow mb-1 flex items-center gap-3">
            <span>Lab notebook · no. 01</span>
            <BrailleRule />
          </div>
          <h1 className="font-display text-5xl leading-none tracking-tight">
            Blind<span className="italic text-touch">grasp</span>
          </h1>
        </div>
        <p className="max-w-xl pb-1 text-[15px] leading-snug text-ink-2">
          A robot arm that <b className="font-semibold text-ink">can&apos;t see</b>. It learns the table by touch, then learns to push a puck in a
          handful of tries — using <span className="font-semibold text-model">TabPFN</span>, a model that learns from examples on the spot, with no training.
        </p>
        <div className="ml-auto flex items-center gap-2 pb-1">
          {state && <span className="stamp tabular-nums">t+{state.t.toFixed(0)}s</span>}
          <span className={clsx("stamp", connected ? "bg-good text-paper" : connected === false ? "bg-alert text-paper" : "")}>
            {connected ? "● live" : connected === false ? "offline" : "connecting"}
          </span>
          <button onClick={onIntro} className="stamp hover:bg-paper-2">what is this?</button>
          <button onClick={onHelp} className="stamp hover:bg-paper-2" title="Keyboard shortcuts">?</button>
        </div>
      </div>
    </header>
  );
}

/* ───────────────────────── act tabs ───────────────────────── */

function ActTabs({ mode, onPick }: { mode?: Mode; onPick: (m: Mode) => void }) {
  return (
    <nav className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="Choose a demo">
      {ACTS.map((a, i) => {
        const on = mode === a.mode;
        return (
          <button key={a.mode} onClick={() => onPick(a.mode)} data-on={on} className={clsx("press flex-col !items-stretch !gap-1 text-left", on && "!bg-ink !text-paper")}>
            <span className="flex items-center justify-between">
              <span className={clsx("font-display text-lg italic", on ? "text-touch" : "text-ink-3")}>{a.n}</span>
              <span className="flex items-center gap-2">
                <Braille dots={a.dots} size={4} gap={2} className={on ? "text-touch" : "text-ink-3"} />
                <span className="key">{i + 1}</span>
              </span>
            </span>
            <span className="text-[15px] font-semibold">{a.title}</span>
            <span className={clsx("text-xs font-normal leading-snug", on ? "text-paper/70" : "text-ink-2")}>{a.blurb}</span>
          </button>
        );
      })}
    </nav>
  );
}

/* ───────────────────────── narrator ───────────────────────── */

const TONE: Record<Tone, { bar: string; label: string }> = {
  info: { bar: "bg-ink", label: "now" },
  think: { bar: "bg-model", label: "thinking" },
  good: { bar: "bg-good", label: "nice" },
  alert: { bar: "bg-touch", label: "heads up" },
};

function Narrator({ state, connected }: { state: SimState | null; connected: boolean | null }) {
  const n = narrate(state, connected);
  const t = TONE[n.tone];
  return (
    <div className="sheet flex" aria-live="polite">
      <div className={clsx("w-2 shrink-0", t.bar)} />
      <div key={n.title} className="flex-1 animate-[fadein_0.3s_ease-out] px-5 py-3">
        <div className="eyebrow mb-1">What&apos;s happening · {t.label}</div>
        <div className="font-display text-[22px] leading-tight">{n.title}</div>
        <p className="mt-0.5 max-w-4xl text-sm leading-relaxed text-ink-2">{n.body}</p>
      </div>
    </div>
  );
}

/* ───────────────────────── beats + key ───────────────────────── */

function BeatTimeline({ beat }: { beat: string | null }) {
  const cur = beat ? Number(beat.trim()[0]) || 1 : 1;
  return (
    <div className="sheet px-5 py-4">
      <div className="eyebrow mb-3">The guided demo, step by step</div>
      <ol className="relative grid grid-cols-5">
        <span className="absolute left-[10%] right-[10%] top-[13px] h-[1.5px] bg-rule" />
        <span className="absolute left-[10%] top-[13px] h-[1.5px] bg-ink transition-all duration-700" style={{ width: `${(Math.min(cur, 5) - 1) * 20}%` }} />
        {BEATS.map((b, i) => {
          const k = i + 1, done = k < cur || cur === 5, on = k === cur && cur !== 5;
          return (
            <li key={b} className="relative flex flex-col items-center gap-2 text-center">
              <span
                className={clsx(
                  "grid h-7 w-7 place-items-center rounded-full border-[1.5px] border-ink font-mono text-xs font-semibold",
                  done ? "bg-ink text-paper" : on ? "bg-touch text-ink" : "bg-card text-ink-3",
                )}
              >
                {done ? "✓" : k}
              </span>
              <span className={clsx("text-xs leading-tight", on ? "font-semibold text-ink" : done ? "text-ink-2" : "text-ink-3")}>{b}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function MapKey({ push }: { push: boolean }) {
  const items: [React.ReactNode, string][] = [
    [<span key="g" className="h-3 w-10 border border-ink" style={{ background: "linear-gradient(90deg,#2659d9,#f2d933,#e6331f)" }} />, "Robot's guess of height: flat → tall"],
    [<span key="f" className="h-3 w-3 border border-ink bg-[#2659d9]/25" />, "Faded tile = it's unsure there"],
    [<span key="o" className="h-3 w-3 rounded-full bg-[#ff8c1a]" />, "Touch that hit something"],
    [<span key="s" className="h-3 w-3 rounded-full bg-[#8c8c8c]" />, "Touch that felt bare table"],
  ];
  if (push) items.push([<span key="p" className="h-3 w-3 rounded-full bg-[#1ae64d]" />, "Green goal / planned push (red = blocked)"]);
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-y-[1.5px] border-dashed border-rule py-2.5 text-xs text-ink-2">
      <span className="eyebrow">Key</span>
      {items.map(([sw, label]) => (
        <span key={label} className="flex items-center gap-2">
          {sw}
          {label}
        </span>
      ))}
    </div>
  );
}

/* ───────────────────────── numbers ───────────────────────── */

function Numbers({ state, push }: { state: SimState | null; push: boolean }) {
  const lc = state?.curve?.at(-1);
  const lp = state?.pushes?.at(-1);
  const ms = state?.fit_s != null ? Math.round(state.fit_s * 1000) : null;
  const think = ms == null ? "–" : ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
  type Cell = { k: string; v: React.ReactNode; sub: string; tip: string; good?: boolean; bad?: boolean };
  const cells: Cell[] = push
    ? [
        { k: "Pushes tried", v: state?.pushes.length ?? 0, sub: `${state?.push_rows ?? 0} remembered`, tip: "Each push becomes one example the model learns from. After a physics change, old examples are thrown away." },
        { k: "Puck to goal", v: lp ? `${lp.goal_cm.toFixed(1)} cm` : "–", sub: "aim: under 3 cm", tip: "How far the puck stopped from the green goal after the last push.", good: lp ? lp.goal_cm < 3 : undefined },
        { k: "Guess was off by", v: lp?.miss_cm != null ? `${lp.miss_cm.toFixed(1)} cm` : "–", sub: lp?.change ? "big miss → physics changed" : "small = it understands the puck", tip: "Before each push the robot predicts where the puck will stop. This is how far off that guess was. A sudden big miss tells it the world changed.", bad: lp?.change },
        { k: "Thinking time", v: think, sub: "per update, no training", tip: "How long TabPFN takes to take in all examples and make a fresh prediction. There is no training step — it learns in one pass." },
      ]
    : [
        { k: "Touches", v: state?.probes ?? 0, sub: `${state?.rows ?? 0} remembered`, tip: "Every time the probe touches the table, it records where and how tall. These are the only examples the model gets." },
        { k: "Map error", v: lc ? `${lc.mae_cm.toFixed(2)} cm` : "–", sub: "aim: under 1 cm", tip: "On average, how far the robot's height map is from the real table, in centimetres.", good: lc ? lc.mae_cm < 1 : undefined },
        { k: "Box shapes found", v: lc ? `${Math.round(lc.iou * 100)}%` : "–", sub: "overlap with real outlines", tip: "How well the boxes it believes in overlap the real ones (100% = perfect outlines). Edges are hard to feel with a round-tipped probe." },
        { k: "Thinking time", v: think, sub: "per update, no training", tip: "How long TabPFN takes to redraw the whole map after a new touch. There is no training step." },
      ];
  return (
    <div className="sheet grid grid-cols-2">
      {cells.map((c, i) => (
        <div key={c.k} className={clsx("px-4 py-3.5", i % 2 === 0 && "border-r-[1.5px] border-ink", i < 2 && "border-b-[1.5px] border-ink")}>
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-medium text-ink-2">{c.k}</span>
            <InfoTip text={c.tip} side="bottom" align={i % 2 ? "right" : "center"} />
          </div>
          <div className={clsx("mt-1 font-mono text-[26px] font-semibold leading-none tracking-tight tabular-nums", c.bad ? "text-alert" : c.good ? "text-good" : "text-ink")}>{c.v}</div>
          <div className={clsx("mt-1.5 text-[11px]", c.bad ? "font-semibold text-alert" : "text-ink-3")}>{c.sub}</div>
        </div>
      ))}
    </div>
  );
}

/* ───────────────────────── controls ───────────────────────── */

type Act = (n: "auto" | "reset" | "truth" | "friction" | "mass") => void;

function TryIt({ state, armed, onArm, act }: { state: SimState | null; armed: boolean; onArm: () => void; act: Act }) {
  const paused = state?.auto === false;
  const fr = state?.friction ?? "normal";
  const frLabel = fr === "normal" ? "Make the table icy" : fr === "low" ? "Make it sticky" : "Table back to normal";
  return (
    <div className="sheet p-4">
      <div className="mb-1 font-display text-xl italic">Try it yourself</div>
      <p className="mb-4 text-xs leading-relaxed text-ink-2">Change the world behind the robot&apos;s back — it&apos;s never told, it has to notice.</p>
      <div className="grid gap-3">
        <div className="grid grid-cols-2 gap-3">
          <button onClick={() => act("auto")} className={clsx("press justify-center", paused && "press-ink")}>
            {paused ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />} {paused ? "Resume" : "Pause"}
          </button>
          <button onClick={() => act("reset")} className="press justify-center">
            <RotateCcw className="h-4 w-4" /> Start over
          </button>
        </div>
        <button onClick={onArm} data-on={armed} className={clsx("press", "press-touch")}>
          <Move className="h-4 w-4" />
          <span className="flex-1 text-left">{armed ? "Now click something in the view…" : "Move a box, the puck or the goal"}</span>
        </button>
        <button onClick={() => act("friction")} className={clsx("press", fr === "low" && "press-model")}>
          <Snowflake className="h-4 w-4" />
          <span className="flex-1 text-left">{frLabel}</span>
          <span className="font-mono text-[11px] opacity-70">now: {fr === "low" ? "icy" : fr === "high" ? "sticky" : "normal"}</span>
        </button>
        <button onClick={() => act("truth")} data-on={state?.truth} className={clsx("press", state?.truth && "!bg-paper-2")}>
          <ScanEye className="h-4 w-4" />
          <span className="flex-1 text-left">{state?.truth ? "Hide the true layout" : "Peek at the true layout"}</span>
        </button>
      </div>
    </div>
  );
}

function Advanced({ state, push, act }: { state: SimState | null; push: boolean; act: Act }) {
  const [open, setOpen] = useState(false);
  const [speed, setSpeed] = useState<number | null>(null);
  const shown = speed ?? state?.speed ?? 2;
  return (
    <div className="sheet">
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center justify-between px-4 py-3 text-left" aria-expanded={open}>
        <span>
          <span className="text-sm font-semibold">For the curious</span>
          <span className="ml-2 text-xs text-ink-3">model, strategy, speed</span>
        </span>
        <ChevronDown className={clsx("h-4 w-4 transition", open && "rotate-180")} />
      </button>
      {open && (
        <div className="grid gap-4 border-t-[1.5px] border-ink p-4">
          <Field label="Learning model" tip="TabPFN is the star. The others are classic methods to compare against: swap and watch the map change.">
            <select value={state?.learner ?? "tabpfn"} onChange={(e) => send({ name: "learner", value: e.target.value })} className="field">
              {Object.entries(LEARNER_LABEL).map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </select>
          </Field>
          {push ? (
            <Field label="When the physics changes…" tip="Reset: forget old pushes right away. Window: only keep the latest few. Never forget: keep everything (slow to adapt).">
              <Seg value={state?.adapt ?? "reset"} onChange={(v) => send({ name: "adapt", value: v })} options={[["reset", "Forget"], ["window", "Recent only"], ["none", "Never forget"]]} />
            </Field>
          ) : (
            <Field label="Where to touch next" tip="Unsure: where the model is least certain (smart). Edges: around box borders. Random and Row-by-row are dumb baselines.">
              <Seg value={state?.strategy ?? "active"} onChange={(v) => send({ name: "strategy", value: v })} options={[["active", "Unsure"], ["lse", "Edges"], ["random", "Random"], ["raster", "Row by row"]]} />
            </Field>
          )}
          <Field label={`Simulation speed · ${shown}×`}>
            <input
              type="range" min={0.5} max={8} step={0.5} value={shown} className="w-full"
              onChange={(e) => {
                const v = Number(e.target.value);
                setSpeed(v);
                send({ name: "speed", value: v });
              }}
              onMouseUp={() => setSpeed(null)}
              onTouchEnd={() => setSpeed(null)}
            />
          </Field>
          <button onClick={() => act("mass")} className="press justify-between">
            <span>Change puck weight</span>
            <span className="font-mono text-[11px] opacity-70">now: {state?.mass ?? "normal"}</span>
          </button>
        </div>
      )}
    </div>
  );
}

function Field({ label, tip, children }: { label: string; tip?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="flex items-center gap-1.5 text-xs font-medium text-ink-2">
        {label}
        {tip && <InfoTip text={tip} align="right" />}
      </span>
      {children}
    </div>
  );
}

function Seg({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: [string, string][] }) {
  return (
    <div className="flex border-[1.5px] border-ink">
      {options.map(([v, l], i) => (
        <button
          key={v}
          type="button"
          onClick={() => onChange(v)}
          className={clsx("flex-1 px-2 py-1.5 text-xs transition", i > 0 && "border-l-[1.5px] border-ink", value === v ? "bg-ink text-paper" : "bg-card hover:bg-paper-2")}
        >
          {l}
        </button>
      ))}
    </div>
  );
}

/* ───────────────────────── charts ───────────────────────── */

function Charts({ state, push }: { state: SimState | null; push: boolean }) {
  const pushes = useMemo(() => state?.pushes ?? [], [state?.pushes]);
  const curve = useMemo(() => state?.curve ?? [], [state?.curve]);
  if (push)
    return (
      <>
        <ChartCard fig="2" title="Getting closer to the goal" note="cm from goal, after each push">
          <LineChart series={{ color: "var(--color-model)", points: pushes.map((p) => ({ x: p.n, y: p.goal_cm, flag: p.change })) }} target={3} unit=" cm" yMax={40} xMin={10} xLabel="push #" emptyLabel="waiting for the first push" />
        </ChartCard>
        <ChartCard fig="3" title="How wrong its guesses were" note="a spike means the world changed">
          <LineChart series={{ color: "var(--color-touch)", points: pushes.map((p) => ({ x: p.n, y: p.miss_cm, flag: p.change })) }} target={1.5} unit=" cm" yMax={12} xMin={10} xLabel="push #" emptyLabel="guesses start after 3 test pushes" />
        </ChartCard>
      </>
    );
  return (
    <>
      <ChartCard fig="2" title="The map gets more accurate" note="average height error, cm">
        <LineChart series={{ color: "var(--color-model)", points: curve.map((p) => ({ x: p.n, y: p.mae_cm })) }} target={1} unit=" cm" yMax={4} xLabel="touches" emptyLabel="waiting for the first touches" />
      </ChartCard>
      <ChartCard fig="3" title="Box shapes come into focus" note="overlap with real outlines">
        <LineChart series={{ color: "var(--color-touch)", points: curve.map((p) => ({ x: p.n, y: p.iou })) }} goodBelow={false} yMax={1} xLabel="touches" emptyLabel="waiting for the first touches" />
      </ChartCard>
    </>
  );
}

function ChartCard({ fig, title, note, children }: { fig: string; title: string; note: string; children: React.ReactNode }) {
  return (
    <figure className="sheet p-4">
      <figcaption className="mb-3">
        <span className="eyebrow">fig. {fig}</span>
        <div className="font-display text-lg leading-tight">{title}</div>
        <div className="text-xs text-ink-3">{note}</div>
      </figcaption>
      {children}
    </figure>
  );
}

/* ───────────────────────── notebook log ───────────────────────── */

const TAGS: [RegExp, string, string][] = [
  [/PRESENTER/, "demo", "bg-[#e7dcff] text-[#4b2a9a]"],
  [/physics changed|missed (its )?prediction|CHANGE CONFIRMED|dropped|surprise/, "change", "bg-touch text-ink"],
  [/route check/, "obstacle", "bg-[#ffe7a3] text-ink"],
  [/map done|reached|finished/, "milestone", "bg-good text-paper"],
  [/new run|learner|mode|adaptation|selected|moved/, "you", "bg-paper-2 text-ink-2"],
];

function Notebook({ events, error }: { events: string[]; error: string | null }) {
  return (
    <div className="sheet flex min-h-0 flex-col">
      <div className="flex items-center justify-between border-b-[1.5px] border-ink px-4 py-3">
        <span className="font-display text-lg italic">Field notes</span>
        <span className="eyebrow">newest first</span>
      </div>
      <ol
        className="max-h-[360px] overflow-y-auto px-4 py-2"
        style={{ backgroundImage: "repeating-linear-gradient(transparent 0 27px, var(--color-rule) 27px 28px)" }}
      >
        {events.length === 0 && <li className="py-2 text-xs italic text-ink-3">Nothing yet…</li>}
        {events.slice().reverse().map((e, i) => {
          const m = e.match(/^\[\s*([\d.]+)s\]\s*(.*)$/);
          const time = m?.[1], text = m?.[2] ?? e;
          const tag = TAGS.find(([re]) => re.test(text));
          return (
            <li key={`${events.length - i}-${e}`} className={clsx("flex gap-3 py-1 text-[13px] leading-[20px]", i === 0 && "animate-[fadein_0.4s_ease-out]")}>
              <span className="w-9 shrink-0 text-right font-mono text-[11px] leading-[20px] text-ink-3">{time ? `${Number(time).toFixed(0)}s` : ""}</span>
              <span className="min-w-0 flex-1 text-ink">
                {tag && <span className={clsx("mr-1.5 px-1.5 py-px font-mono text-[10px] font-semibold uppercase", tag[2])}>{tag[1]}</span>}
                {text.replace(/^PRESENTER:\s*/, "")}
              </span>
            </li>
          );
        })}
      </ol>
      {error && <pre className="m-3 mt-0 whitespace-pre-wrap border-[1.5px] border-alert bg-alert/10 p-2 font-mono text-[11px] text-alert">{error}</pre>}
    </div>
  );
}

/* ───────────────────────── modals ───────────────────────── */

function Modal({ onClose, children, wide }: { onClose: () => void; children: React.ReactNode; wide?: boolean }) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4" onClick={onClose}>
      <div className={clsx("sheet max-h-[90vh] w-full overflow-y-auto p-6", wide ? "max-w-2xl" : "max-w-md")} style={{ boxShadow: "8px 8px 0 0 var(--color-ink)" }} onClick={(e) => e.stopPropagation()}>
        {children}
      </div>
    </div>
  );
}

function Intro({ onClose }: { onClose: () => void }) {
  const steps = [
    { icon: <Hand className="h-5 w-5" />, h: "It's blind", p: "No camera. The arm only knows what it has touched — each touch gives one height at one spot." },
    { icon: <Braille dots={[1, 2, 4, 5]} size={5} gap={3} />, h: "It learns from examples, instantly", p: "TabPFN takes every touch (or push) so far and predicts the rest — with error bars — in about a second. No training." },
    { icon: <Snowflake className="h-5 w-5" />, h: "You can surprise it", p: "Move a box or make the table icy. The robot isn't told; it notices when the world stops matching what it predicted." },
  ];
  return (
    <Modal onClose={onClose} wide>
      <div className="eyebrow mb-2 flex items-center gap-3">Welcome <BrailleRule /></div>
      <h2 className="font-display text-3xl leading-tight">A robot arm that learns its world <span className="italic text-touch">by touch</span>.</h2>
      <ol className="mt-6 grid gap-4 sm:grid-cols-3">
        {steps.map((s, i) => (
          <li key={s.h} className="border-t-[1.5px] border-ink pt-3">
            <div className="mb-2 flex items-center gap-2 text-ink">
              <span className="font-display text-xl italic text-ink-3">{i + 1}.</span>
              {s.icon}
            </div>
            <div className="font-semibold">{s.h}</div>
            <p className="mt-1 text-sm leading-relaxed text-ink-2">{s.p}</p>
          </li>
        ))}
      </ol>
      <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t-[1.5px] border-dashed border-rule pt-4">
        <span className="text-xs text-ink-3">Tip: the big sentence above the video always explains what&apos;s going on.</span>
        <button onClick={onClose} className="press press-ink">Got it — show me</button>
      </div>
    </Modal>
  );
}

function Shortcuts({ onClose }: { onClose: () => void }) {
  const rows: [string, string][] = [
    ["Space", "pause / resume"],
    ["R", "start over"],
    ["F", "table: normal → icy → sticky"],
    ["T", "peek at the true layout"],
    ["M", "change puck weight"],
    ["1 – 4", "switch demo"],
    ["drag", "look around"],
    ["⌘/ctrl + scroll", "zoom"],
    ["Esc", "close / cancel"],
  ];
  return (
    <Modal onClose={onClose}>
      <h2 className="mb-4 font-display text-2xl italic">Shortcuts</h2>
      <dl className="grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-2 text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt><span className="key !text-[11px] !opacity-100">{k}</span></dt>
            <dd className="text-ink-2">{v}</dd>
          </div>
        ))}
      </dl>
      <button onClick={onClose} className="press mt-5">Close</button>
    </Modal>
  );
}
