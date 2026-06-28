import { ValueRow } from "../api";
import { kickoff, pct, signedPct } from "../lib/format";

function StatusTag({ status, utc }: { status: string; utc: string | null }) {
  if (status === "live")
    return <span className="chip font-display bg-floodlight/15 text-floodlight">LIVE</span>;
  if (status === "finished")
    return <span className="chip font-display bg-ink-700 text-slate-400">FT</span>;
  return <span className="numeric text-[10px] text-slate-500">{kickoff(utc)}</span>;
}

// Consolidated "where the model and the book disagree most" — informational
// edge signals only, sorted biggest-first. Not betting advice.
export function ValueBoard({ rows }: { rows: ValueRow[] }) {
  return (
    <div className="card overflow-hidden">
      <div className="chrome-glass flex items-center justify-between border-b border-white/[0.06] px-4 py-3">
        <h2 className="flex items-center gap-2 font-display text-sm font-semibold uppercase tracking-[0.08em] text-slate-100">
          <span className="h-1.5 w-1.5 rounded-full bg-win" />
          Value board
        </h2>
        <span className="label">Model vs market</span>
      </div>

      {rows.length === 0 ? (
        <div className="p-4 text-[12px] text-slate-500">
          No value edges right now — the model and the books broadly agree. This is an
          informational signal, not advice.
        </div>
      ) : (
        <ul className="divide-y divide-white/[0.05]">
          {rows.map((r, i) => (
            <li key={`${r.match_id}-${i}`} className="flex items-center gap-3 px-4 py-2.5">
              <div className="min-w-0 flex-1">
                <div className="truncate text-[13px] font-medium text-slate-100">{r.outcome}</div>
                <div className="mt-0.5 flex items-center gap-2 text-[10.5px] text-slate-500">
                  <span className="truncate">
                    {r.home} v {r.away}
                  </span>
                  <StatusTag status={r.status} utc={r.utc_date} />
                </div>
              </div>
              <div className="shrink-0 text-right">
                <div className="numeric text-sm font-semibold text-win">{signedPct(r.edge)}</div>
                <div className="numeric text-[10px] text-slate-500">
                  {pct(r.model_pct)} vs {pct(r.market_pct)}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
      <div className="bg-ink-800/40 px-4 py-1.5 text-[10px] text-slate-500">
        Edge = model % − sportsbook implied %. Information only, not advice.
      </div>
    </div>
  );
}
