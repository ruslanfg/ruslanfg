import { MarketComparison } from "../api";
import { DASH, pct, signedPct } from "../lib/format";

// Per-outcome comparison: Model % vs Sportsbook implied % vs Polymarket %,
// with a "value" edge flag where the model materially exceeds the book.
export function MarketTable({ market }: { market: MarketComparison }) {
  if (!market.sportsbook_available && !market.polymarket_available) {
    return (
      <div className="rounded-lg border border-white/[0.05] bg-ink-800/50 px-3 py-2 text-[12px] italic text-slate-500">
        {market.note || "Market data unavailable"}
      </div>
    );
  }
  return (
    <div className="overflow-hidden rounded-lg border border-white/[0.06]">
      <table className="w-full">
        <thead className="bg-ink-800/60">
          <tr>
            <th className="th">Outcome</th>
            <th className="th text-right">Model</th>
            <th className="th text-right">
              Book{market.sportsbook_book ? ` · ${market.sportsbook_book}` : ""}
            </th>
            <th className="th text-right">Poly</th>
            <th className="th text-right">Edge</th>
          </tr>
        </thead>
        <tbody>
          {market.outcomes.map((row) => {
            const flagged = row.value.flagged;
            return (
              <tr
                key={row.key}
                className={`group relative ${flagged ? "bg-win/[0.06] hover:bg-win/[0.1]" : ""}`}
              >
                <td className="td relative text-slate-300">
                  {flagged && (
                    <span className="absolute inset-y-0 left-0 w-[2px] bg-win transition-all group-hover:shadow-[0_0_8px_rgba(52,211,153,0.7)]" />
                  )}
                  {row.label}
                </td>
                <td className="td numeric text-right text-slate-100">{pct(row.model_pct)}</td>
                <td className="td numeric text-right text-slate-300">{pct(row.sportsbook_pct)}</td>
                <td className="td numeric text-right text-slate-300">{pct(row.polymarket_pct)}</td>
                <td className={`td text-right ${flagged ? "text-win" : "text-slate-500"}`}>
                  <span className="numeric font-medium">
                    {row.value.edge === null ? DASH : signedPct(row.value.edge)}
                  </span>
                  {flagged && (
                    <span className="ml-1 inline-flex items-center gap-0.5 align-middle font-display text-[8.5px] tracking-wide transition-transform group-hover:scale-105">
                      <span>●</span>VALUE
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="bg-ink-800/40 px-3 py-1.5 text-[10.5px] text-slate-500">
        “Edge” = model % − sportsbook implied %. A flagged row is an informational
        signal only — not advice, not a guarantee.
      </div>
    </div>
  );
}
