import { Wallet } from "../api";
import { addr, pct, signed } from "../lib/format";

export default function WalletLeaderboard({
  wallets,
  topN = 5,
}: {
  wallets: Wallet[];
  topN?: number;
}) {
  const ranked = wallets
    .filter((w) => w.rank != null)
    .sort((a, b) => (a.rank! - b.rank!))
    .slice(0, 12);

  return (
    <div className="card animate-fade-in overflow-hidden">
      <div className="flex items-center justify-between card-pad pb-3">
        <div>
          <div className="label">Tracked wallet leaderboard</div>
          <div className="text-xs text-slate-500 mt-0.5">
            ranked by score · top {topN} are mirrored
          </div>
        </div>
        <span className="text-xs text-slate-500">{wallets.length} tracked</span>
      </div>
      <div className="overflow-x-auto">
        {ranked.length === 0 ? (
          <div className="grid place-items-center py-12 text-sm text-slate-600">
            No wallets meet the minimum-trades bar yet
          </div>
        ) : (
          <table className="w-full">
            <thead>
              <tr>
                <th className="th">#</th>
                <th className="th">Wallet</th>
                <th className="th">Win rate</th>
                <th className="th text-right">Trades</th>
                <th className="th text-right">Realized</th>
                <th className="th">Score</th>
              </tr>
            </thead>
            <tbody>
              {ranked.map((w) => {
                const mirrored = (w.rank ?? 99) <= topN;
                return (
                  <tr
                    key={w.wallet}
                    className={`hover:bg-white/[0.02] ${mirrored ? "bg-accent/[0.04]" : ""}`}
                  >
                    <td className="td">
                      <span
                        className={`grid h-6 w-6 place-items-center rounded-md text-xs font-bold ${
                          mirrored ? "bg-accent/20 text-accent" : "bg-ink-700 text-slate-400"
                        }`}
                      >
                        {w.rank}
                      </span>
                    </td>
                    <td className="td">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs text-slate-300">{addr(w.wallet)}</span>
                        {mirrored && (
                          <span className="rounded bg-accent/15 px-1.5 py-0.5 text-[10px] font-medium text-accent">
                            copying
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="td w-40">
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-16 overflow-hidden rounded-full bg-ink-700">
                          <div className="h-full bg-up/70" style={{ width: `${Math.min(100, w.win_rate * 100)}%` }} />
                        </div>
                        <span className="text-xs text-slate-300 nums">{pct(w.win_rate)}</span>
                      </div>
                    </td>
                    <td className="td text-right nums text-slate-400">{w.trades_count}</td>
                    <td className={`td text-right nums ${w.realized_pnl >= 0 ? "text-up" : "text-down"}`}>
                      {signed(w.realized_pnl, 0)}
                    </td>
                    <td className="td w-28">
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-12 overflow-hidden rounded-full bg-ink-700">
                          <div className="h-full bg-accent/70" style={{ width: `${Math.min(100, w.score * 100)}%` }} />
                        </div>
                        <span className="text-xs text-slate-400 nums">{w.score.toFixed(2)}</span>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
