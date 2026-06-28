import { MarketComparison } from "../api";
import { DASH, pct, signedPct } from "../lib/format";

// Per-outcome comparison: Model % vs Sportsbook implied % vs Polymarket %,
// with a "value" edge flag where the model materially exceeds the book.
export function MarketTable({ market }: { market: MarketComparison }) {
  if (!market.sportsbook_available && !market.polymarket_available) {
    return (
      <div className="rounded-lg bg-ink-800/60 px-3 py-2 text-[12px] text-slate-500">
        {market.note || "Market data unavailable"}
      </div>
    );
  }
  return (
    <div className="overflow-hidden rounded-lg border border-white/[0.05]">
      <table className="w-full nums">
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
              <tr key={row.key} className={flagged ? "bg-win/[0.07]" : ""}>
                <td className="td text-slate-300">{row.label}</td>
                <td className="td text-right text-slate-200">{pct(row.model_pct)}</td>
                <td className="td text-right text-slate-300">{pct(row.sportsbook_pct)}</td>
                <td className="td text-right text-slate-300">{pct(row.polymarket_pct)}</td>
                <td
                  className={`td text-right font-medium ${
                    flagged ? "text-win" : "text-slate-500"
                  }`}
                >
                  {row.value.edge === null ? DASH : signedPct(row.value.edge)}
                  {flagged && <span className="ml-1" title="Model edge vs book">●</span>}
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
