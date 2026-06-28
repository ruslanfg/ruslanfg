import { Suspense, lazy, useEffect, useRef, useState } from "react";
import { Dashboard } from "../api";
import { agoFromUnix } from "../lib/format";
import { CssBall } from "./CssBall";

// Lazy-load the entire 3D module into its own chunk so three/drei never block
// first paint or the data fetch. The CSS ball is the Suspense fallback.
const HeroBall = lazy(() => import("./HeroBall"));

function useMobile() {
  const [mobile, setMobile] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 768px)");
    const sync = () => setMobile(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);
  return mobile;
}

// One-time count-up on first load; thereafter snaps to the live value.
function useCountUp(value: number, durationMs = 850) {
  const [display, setDisplay] = useState(value);
  const done = useRef(false);
  useEffect(() => {
    if (done.current) {
      setDisplay(value);
      return;
    }
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setDisplay(value);
      done.current = true;
      return;
    }
    let raf = 0;
    const start = performance.now();
    const from = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs);
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplay(Math.round(from + (value - from) * eased));
      if (t < 1) raf = requestAnimationFrame(tick);
      else done.current = true;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, durationMs]);
  return display;
}

function Kpi({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  // `accent` (live state) is conveyed via chrome only — the cyan ring + label.
  // The numeric value itself stays neutral (cyan must never color a number).
  return (
    <div className={`chrome-glass rounded-xl px-3 py-2 ${accent ? "ring-1 ring-floodlight/40" : ""}`}>
      <div className={`label text-[9.5px] ${accent ? "text-floodlight" : "text-slate-500"}`}>{label}</div>
      <div className="numeric text-lg font-semibold text-slate-100">{value}</div>
    </div>
  );
}

export function HeroBand({ data, refreshTick }: { data: Dashboard | null; refreshTick: number }) {
  const mobile = useMobile();
  const live = useCountUp(data?.live_count ?? 0);
  const value = useCountUp(data?.value_count ?? 0);
  const t = data?.tournament;

  const ballSize = mobile ? 190 : 300;

  return (
    <section
      className="relative mx-auto mb-2 max-w-7xl overflow-hidden px-4 sm:px-6"
      style={{ height: mobile ? "auto" : "clamp(250px, 34vh, 360px)" }}
      aria-label="Tournament hero"
    >
      {/* stadium staging — pure CSS, sits behind the transparent ball canvas */}
      <div className="pointer-events-none absolute inset-0" aria-hidden>
        <div
          className="absolute"
          style={{
            right: mobile ? "50%" : "16%",
            top: mobile ? "8%" : "50%",
            transform: mobile ? "translateX(50%)" : "translateY(-50%)",
            width: 520,
            height: 520,
            maxWidth: "90vw",
            background:
              "radial-gradient(closest-side, rgba(56,225,214,0.12), rgba(214,232,255,0.06) 40%, transparent 70%)",
            filter: "blur(8px)",
          }}
        />
        {!mobile && (
          <div
            className="absolute right-[6%] top-0 h-full w-[55%] opacity-40"
            style={{
              background:
                "conic-gradient(from 200deg at 70% -10%, transparent 0deg, rgba(214,232,255,0.10) 12deg, transparent 26deg, transparent 200deg, rgba(56,225,214,0.07) 220deg, transparent 240deg)",
              maskImage: "linear-gradient(to bottom, black, transparent 85%)",
            }}
          />
        )}
        <div className="absolute inset-0 shadow-[inset_0_0_120px_40px_rgba(0,0,0,0.55)]" />
      </div>

      <div
        className={`relative flex h-full ${
          mobile ? "flex-col items-center gap-3 py-4" : "flex-row items-center justify-between gap-6"
        }`}
      >
        {/* title block */}
        <div className={`${mobile ? "order-2 text-center" : "max-w-[55%]"}`}>
          <h1 className="font-display text-[clamp(28px,5vw,46px)] font-bold leading-[0.95] text-slate-50">
            {t?.name || "FIFA World Cup 2026"}
          </h1>
          <p className="mt-1.5 text-[12px] uppercase tracking-[0.16em] text-slate-400">
            Prediction &amp; Market Dashboard
          </p>
          <p className="mt-0.5 text-[12px] text-slate-500">
            {t ? `${t.hosts} · ${t.window}` : "USA · Canada · Mexico"}
          </p>

          <div className="mt-4 flex flex-wrap gap-2">
            <Kpi label="Live now" value={String(live)} accent={live > 0} />
            <Kpi label="Value flags" value={String(value)} />
            <Kpi label="Updated" value={data?.updated_at ? agoFromUnix(data.updated_at) : "—"} />
          </div>
        </div>

        {/* 3D ball stage */}
        <div className={`${mobile ? "order-1" : ""} relative grid shrink-0 place-items-center`}>
          <Suspense fallback={<CssBall size={ballSize} />}>
            <HeroBall size={ballSize} refreshTick={refreshTick} />
          </Suspense>
        </div>
      </div>
    </section>
  );
}
