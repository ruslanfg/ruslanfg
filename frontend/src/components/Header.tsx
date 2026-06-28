import { useState } from "react";
import { Dashboard } from "../api";
import { ConnState } from "../hooks/useDashboard";
import { agoFromUnix } from "../lib/format";

export function Header({
  data,
  conn,
  refreshing,
  onRefresh,
}: {
  data: Dashboard | null;
  conn: ConnState;
  refreshing: boolean;
  onRefresh: () => void;
}) {
  const t = data?.tournament;
  const liveActive = (data?.live_count ?? 0) > 0;
  const [sweep, setSweep] = useState(false);

  const handleRefresh = () => {
    setSweep(true);
    window.setTimeout(() => setSweep(false), 750);
    onRefresh();
  };

  return (
    <header className="sticky top-0 z-20 border-b border-white/[0.06] chrome-glass bg-ink-950/85">
      <div className="relative mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
        <div className="min-w-0">
          <h1 className="font-display text-base font-semibold uppercase tracking-[0.05em] text-slate-100 sm:text-lg">
            {t?.name || "FIFA World Cup 2026"}
            <span className="ml-2 font-sans text-xs font-normal normal-case tracking-normal text-slate-500">
              prediction &amp; market dashboard
            </span>
          </h1>
          <p className="text-[11px] text-slate-500">
            {t ? `${t.hosts} · ${t.window}` : "USA · Canada · Mexico"}
          </p>
        </div>

        <div className="flex items-center gap-3">
          {data && (
            <div className="hidden text-right sm:block">
              <div className="flex items-center justify-end gap-2 text-xs">
                {liveActive && (
                  <span className="chip bg-floodlight/15 text-floodlight">
                    <span className="h-1.5 w-1.5 rounded-full bg-floodlight animate-live-beat" />
                    <span className="numeric">{data.live_count}</span> live
                  </span>
                )}
                {data.value_count > 0 && (
                  <span className="chip bg-win/10 text-win">
                    <span className="numeric">{data.value_count}</span> value flags
                  </span>
                )}
              </div>
              <div className="mt-0.5 text-[10.5px] text-slate-500">
                updated <span className="numeric">{agoFromUnix(data.updated_at)}</span>
              </div>
            </div>
          )}
          <span
            className={`chip ${
              conn === "live"
                ? "bg-win/10 text-win"
                : conn === "offline"
                ? "bg-loss/10 text-loss"
                : "bg-ink-700 text-slate-400"
            }`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                conn === "live"
                  ? "bg-win animate-live-beat"
                  : conn === "offline"
                  ? "bg-loss"
                  : "bg-slate-500"
              }`}
            />
            {conn}
          </span>
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="relative overflow-hidden rounded-lg border border-white/10 bg-ink-800 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-ink-700 disabled:opacity-50"
          >
            {sweep && (
              <span className="pointer-events-none absolute inset-y-0 -left-full w-full animate-sweep bg-gradient-to-r from-transparent via-floodlight/30 to-transparent" />
            )}
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </div>
      {/* cyan scoreboard underline only while something is live */}
      {liveActive && <div className="h-px w-full bg-floodlight/50" />}
    </header>
  );
}
