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
  return (
    <header className="sticky top-0 z-20 border-b border-white/[0.06] bg-ink-950/85 backdrop-blur">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
        <div className="min-w-0">
          <h1 className="text-base font-semibold tracking-tight text-slate-100 sm:text-lg">
            {t?.name || "FIFA World Cup 2026"}
            <span className="ml-2 text-xs font-normal text-slate-500">
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
                {data.live_count > 0 && (
                  <span className="chip bg-loss/15 text-loss">
                    <span className="h-1.5 w-1.5 rounded-full bg-loss animate-pulse-dot" />
                    {data.live_count} live
                  </span>
                )}
                {data.value_count > 0 && (
                  <span className="chip bg-win/10 text-win">{data.value_count} value flags</span>
                )}
              </div>
              <div className="mt-0.5 text-[10.5px] text-slate-500">
                updated {agoFromUnix(data.updated_at)}
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
                conn === "live" ? "bg-win animate-pulse-dot" : conn === "offline" ? "bg-loss" : "bg-slate-500"
              }`}
            />
            {conn}
          </span>
          <button
            onClick={onRefresh}
            disabled={refreshing}
            className="rounded-lg border border-white/10 bg-ink-800 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-ink-700 disabled:opacity-50"
          >
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </div>
    </header>
  );
}
