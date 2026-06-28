import { SmartMoney as SmartMoneyData, Trader } from "../api";
import { DASH, money, pct, shortAddr } from "../lib/format";

function Positions({ t }: { t: Trader }) {
  if (t.positions === null) {
    return <div className="text-[11px] text-slate-500">{t.positions_note || "positions unavailable"}</div>;
  }
  if (t.positions.length === 0) {
    return <div className="text-[11px] text-slate-500 italic">no current World Cup position</div>;
  }
  return (
    <ul className="mt-1 space-y-1">
      {t.positions.map((p, i) => (
        <li key={i} className="rounded-md bg-ink-800/60 px-2 py-1 text-[11px]">
          <div className="flex items-center justify-between gap-2">
            <span className="truncate text-slate-300">{p.market_title || "Market"}</span>
            {p.outcome && (
              <span className="shrink-0 chip bg-accent/10 text-accent">{p.outcome}</span>
            )}
          </div>
          <div className="mt-0.5 flex flex-wrap gap-x-3 text-[10.5px] text-slate-500 nums">
            {p.value_usd !== null && <span>value {money(p.value_usd)}</span>}
            {p.cur_price !== null && <span>@ {pct(p.cur_price)}</span>}
            {p.unrealized_pnl !== null && (
              <span className={p.unrealized_pnl >= 0 ? "text-win" : "text-loss"}>
                uPnL {money(p.unrealized_pnl)}
              </span>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}

export function SmartMoneyPanel({ data }: { data: SmartMoneyData }) {
  return (
    <div className="card p-4">
      <div className="mb-1 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-100">Smart money</h2>
        <span className="label">Polymarket leaderboard</span>
      </div>
      <p className="mb-3 text-[11px] text-slate-500">
        Top public traders by P&amp;L and the World Cup positions they have{" "}
        <span className="text-slate-400">already taken</span> (public data). Future bets are
        never predicted or inferred.
      </p>

      {!data.available ? (
        <div className="rounded-lg bg-ink-800/60 px-3 py-3 text-[12px] text-slate-500">
          {data.note || "Leaderboard data unavailable"}
        </div>
      ) : (
        <div className="space-y-2.5">
          {data.note && <div className="text-[11px] text-amber-300/80">{data.note}</div>}
          {data.leaderboard.length === 0 && (
            <div className="text-[12px] text-slate-500">No traders returned.</div>
          )}
          {data.leaderboard.map((t) => (
            <div key={t.address} className="border-t border-white/[0.05] pt-2.5 first:border-0 first:pt-0">
              <div className="flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <span className="w-5 shrink-0 text-[11px] text-slate-500 nums">
                    {t.rank ?? DASH}
                  </span>
                  <span className="truncate text-sm text-slate-200">
                    {t.display || shortAddr(t.address)}
                  </span>
                </div>
                <div className="shrink-0 text-right nums">
                  <div className={`text-sm font-semibold ${(t.pnl ?? 0) >= 0 ? "text-win" : "text-loss"}`}>
                    {money(t.pnl)}
                  </div>
                  <div className="text-[10px] text-slate-500">vol {money(t.volume)}</div>
                </div>
              </div>
              <div className="mt-1 pl-7">
                <Positions t={t} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
