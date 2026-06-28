import { SourceStatus } from "../api";
import { agoFromUnix } from "../lib/format";

// Compact strip showing each data source's health, so a degraded/unavailable
// source is always visible rather than silently producing blanks.
export function SourceHealth({ sources }: { sources: SourceStatus[] }) {
  if (!sources || sources.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="label">Sources</span>
      {sources.map((s) => (
        <span
          key={s.name}
          className={`chip ${s.ok ? "bg-win/10 text-win" : "bg-loss/10 text-loss"}`}
          title={`${s.label}: ${s.detail || ""}${
            s.last_ok_at ? ` · last ok ${agoFromUnix(s.last_ok_at)}` : ""
          }`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${s.ok ? "bg-win" : "bg-loss"}`} />
          {s.label.split(" (")[0]}
        </span>
      ))}
    </div>
  );
}
