"use client";

import clsx from "clsx";
import { useCallback, useEffect, useState } from "react";

/** Small (?) with a hover/focus explanation. */
export function InfoTip({ text, side = "bottom", align = "center" }: { text: string; side?: "top" | "bottom"; align?: "center" | "right" | "left" }) {
  return (
    <span className="group/tip relative inline-flex align-middle">
      <button
        type="button"
        aria-label={text}
        className="grid h-3.5 w-3.5 place-items-center rounded-full border border-fg-3 font-mono text-[9px] leading-none text-fg-3 outline-none transition hover:border-fg hover:text-fg focus-visible:border-model focus-visible:text-model"
      >
        ?
      </button>
      <span
        role="tooltip"
        className={clsx(
          "pointer-events-none absolute z-50 w-64 rounded-[3px] border border-line-2 bg-panel-2 px-3 py-2 text-left font-sans text-xs normal-case leading-relaxed tracking-normal text-fg opacity-0 shadow-[0_8px_24px_rgba(0,0,0,0.5)] transition group-hover/tip:opacity-100 group-focus-within/tip:opacity-100",
          side === "top" ? "bottom-full mb-2" : "top-full mt-2",
          align === "right" ? "right-0" : align === "left" ? "left-0" : "left-1/2 -translate-x-1/2",
        )}
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
    <div className="pointer-events-none fixed bottom-9 right-4 z-50 flex w-[min(92vw,360px)] flex-col gap-2" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className="animate-[fadein_0.2s_ease-out] rounded-[3px] border border-line-2 border-l-2 border-l-model bg-panel-2 px-3 py-2.5 shadow-[0_10px_30px_rgba(0,0,0,0.55)]">
          <div className="text-[13px] font-medium text-fg">{t.title}</div>
          {t.body && <div className="mt-0.5 text-xs leading-relaxed text-fg-2">{t.body}</div>}
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
