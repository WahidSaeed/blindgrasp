"use client";

import clsx from "clsx";
import { useCallback, useEffect, useState } from "react";

/** A braille cell. `dots` uses standard numbering: 1 2 3 down the left column, 4 5 6 down the right. */
export function Braille({ dots, size = 5, gap = 3, className }: { dots: number[]; size?: number; gap?: number; className?: string }) {
  const order = [1, 4, 2, 5, 3, 6];
  return (
    <span className={clsx("inline-grid grid-cols-2", className)} style={{ gap }} aria-hidden>
      {order.map((d) => (
        <span
          key={d}
          className={clsx("rounded-full", dots.includes(d) ? "bg-current" : "border border-current opacity-25")}
          style={{ width: size, height: size }}
        />
      ))}
    </span>
  );
}

/** "BLIND" spelled in braille, as a decorative divider. */
export function BrailleRule({ className }: { className?: string }) {
  const word = [[1, 2], [1, 2, 3], [2, 4], [1, 3, 4, 5], [1, 4, 5]]; // b l i n d
  return (
    <span className={clsx("inline-flex items-center gap-2 text-ink-3", className)} aria-hidden>
      {word.map((d, i) => (
        <Braille key={i} dots={d} size={3.5} gap={2} />
      ))}
    </span>
  );
}

/** Small (i) with a hover/focus explanation, styled as a margin note. */
export function InfoTip({ text, side = "top", align = "center" }: { text: string; side?: "top" | "bottom"; align?: "center" | "right" }) {
  return (
    <span className="group/tip relative inline-flex align-middle">
      <button
        type="button"
        aria-label={text}
        className="grid h-4 w-4 place-items-center rounded-full border border-ink-3 font-display text-[10px] italic leading-none text-ink-3 outline-none transition hover:border-ink hover:bg-ink hover:text-paper focus-visible:border-ink focus-visible:bg-ink focus-visible:text-paper"
      >
        i
      </button>
      <span
        role="tooltip"
        className={clsx(
          "pointer-events-none absolute z-40 w-64 border-[1.5px] border-ink bg-card px-3 py-2 text-left font-sans text-xs normal-case leading-relaxed tracking-normal text-ink opacity-0 transition group-hover/tip:opacity-100 group-focus-within/tip:opacity-100",
          side === "top" ? "bottom-full mb-2" : "top-full mt-2",
          align === "right" ? "right-0" : "left-1/2 -translate-x-1/2",
        )}
        style={{ boxShadow: "3px 3px 0 0 var(--color-ink)" }}
      >
        {text}
      </span>
    </span>
  );
}

export interface Toast {
  id: number;
  title: string;
  body?: string;
}

/** Tiny toast queue: returns [toasts, push]. Toasts disappear after 5 s. */
export function useToasts(): [Toast[], (t: Omit<Toast, "id">) => void] {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((t: Omit<Toast, "id">) => {
    const id = Date.now() + Math.random();
    setToasts((ts) => [...ts.slice(-2), { ...t, id }]);
    setTimeout(() => setToasts((ts) => ts.filter((x) => x.id !== id)), 5000);
  }, []);
  return [toasts, push];
}

export function Toasts({ toasts }: { toasts: Toast[] }) {
  return (
    <div className="pointer-events-none fixed bottom-6 right-6 z-50 flex w-[min(92vw,380px)] flex-col gap-3" aria-live="polite">
      {toasts.map((t) => (
        <div
          key={t.id}
          className="animate-[fadein_0.2s_ease-out] -rotate-[0.6deg] border-[1.5px] border-ink bg-[#fff6c9] px-4 py-3"
          style={{ boxShadow: "4px 4px 0 0 var(--color-ink)" }}
        >
          <div className="font-display text-base italic text-ink">{t.title}</div>
          {t.body && <div className="mt-1 text-xs leading-relaxed text-ink-2">{t.body}</div>}
        </div>
      ))}
    </div>
  );
}

/** localStorage-backed boolean; null until mounted so the server and first client render match. */
export function useStoredFlag(key: string): [boolean | null, (v: boolean) => void] {
  const [v, setV] = useState<boolean | null>(null);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- read once from localStorage after mount
    setV(localStorage.getItem(key) === "1");
  }, [key]);
  const set = useCallback(
    (nv: boolean) => {
      localStorage.setItem(key, nv ? "1" : "0");
      setV(nv);
    },
    [key],
  );
  return [v, set];
}
