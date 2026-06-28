import { SourceStatus } from "../api";
import { agoFromUnix } from "../lib/format";

// Compact hairline status row, so a degraded/unavailable source is always
// visible rather than silently producing blanks. Color is never the sole
// signal — the detail text (incl. "data unavailable") is kept verbatim.
export function SourceHealth({ sources }: { sources: SourceStatus[] }) {
  if (!sources || sources.length === 0) return null;
  const lastSync = sources.reduce<number | null>(
    (acc, s) => (s.last_ok_at && (!acc || s.last_ok_at > acc) ? s.last_ok_at : acc),
    null
  );
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-white/[0.05] bg-ink-900/40 px-3 py-2">
      <span className="label">Sources</span>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
        {sources.map((s) => (
          <span
            key={s.name}
            className="flex items-center gap-1.5 text-[11.5px] text-slate-400"
            title={`${s.label}: ${s.detail || ""}`}
          >
            <span
              className={`h-1.5 w-1.5 shrink-0 rounded-full ${s.ok ? "bg-win" : "bg-loss"}`}
            />
            {s.label.split(" (")[0]}
            {!s.ok && <span className="text-loss/80">· {s.detail}</span>}
          </span>
        ))}
      </div>
      {lastSync && (
        <span className="numeric ml-auto text-[10.5px] text-slate-600">
          synced {agoFromUnix(lastSync)}
        </span>
      )}
    </div>
  );
}
