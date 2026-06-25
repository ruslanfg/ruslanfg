import { ClosedPosition, OpenPosition } from "../api";
import { addr, signed, timeAgo, usd } from "../lib/format";

export function OutcomeBadge({ o }: { o: string | null }) {
  const up = o === "UP";
  return (
    <span
      className={`inline-block rounded-md px-2 py-0.5 text-xs font-semibold ${
        up ? "bg-up/15 text-up" : "bg-down/15 text-down"
      }`}
    >
      {o ?? "—"}
    </span>
  );
}

const Empty = ({ children }: { children: React.ReactNode }) => (
  <div className="grid place-items-center py-12 text-sm text-slate-600">{children}</div>
);

export function OpenPositions({ rows }: { rows: OpenPosition[] }) {
  return (
    <div className="card animate-fade-in overflow-hidden">
      <div className="flex items-center justify-between card-pad pb-3">
        <div className="label">Open positions</div>
        <span className="text-xs text-slate-500">{rows.length}</span>
      </div>
      <div className="overflow-x-auto">
        {rows.length === 0 ? (
          <Empty>No open paper positions</Empty>
        ) : (
          <table className="w-full">
            <thead>
              <tr>
                <th className="th">Side</th>
                <th className="th">Copied</th>
                <th className="th text-right">Entry</th>
                <th className="th text-right">Now</th>
                <th className="th text-right">Size</th>
                <th className="th text-right">Unreal. PnL</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.id} className="hover:bg-white/[0.02]">
                  <td className="td"><OutcomeBadge o={p.outcome} /></td>
                  <td className="td font-mono text-xs text-slate-400">{addr(p.source_wallet)}</td>
                  <td className="td text-right nums">{p.entry_price.toFixed(3)}</td>
                  <td className="td text-right nums">{p.current_price?.toFixed(3) ?? "—"}</td>
                  <td className="td text-right nums">{usd(p.size_usd)}</td>
                  <td className={`td text-right nums font-medium ${p.unrealized_pnl >= 0 ? "text-up" : "text-down"}`}>
                    {signed(p.unrealized_pnl)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export function ClosedTrades({ rows }: { rows: ClosedPosition[] }) {
  return (
    <div className="card animate-fade-in overflow-hidden">
      <div className="flex items-center justify-between card-pad pb-3">
        <div className="label">Trade history</div>
        <span className="text-xs text-slate-500">{rows.length}</span>
      </div>
      <div className="overflow-x-auto max-h-[420px] overflow-y-auto">
        {rows.length === 0 ? (
          <Empty>No closed trades yet</Empty>
        ) : (
          <table className="w-full">
            <thead className="sticky top-0 bg-ink-850/95 backdrop-blur">
              <tr>
                <th className="th">Side</th>
                <th className="th">Result</th>
                <th className="th">Copied</th>
                <th className="th text-right">Entry</th>
                <th className="th text-right">Exit</th>
                <th className="th text-right">PnL</th>
                <th className="th text-right">Closed</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => {
                const win = (p.pnl ?? 0) >= 0;
                return (
                  <tr key={p.id} className="hover:bg-white/[0.02]">
                    <td className="td"><OutcomeBadge o={p.outcome} /></td>
                    <td className="td">
                      <span className={`text-xs font-medium ${win ? "text-up" : "text-down"}`}>
                        {win ? "WIN" : "LOSS"} · {p.resolved_outcome ?? "—"}
                      </span>
                    </td>
                    <td className="td font-mono text-xs text-slate-400">{addr(p.source_wallet)}</td>
                    <td className="td text-right nums">{p.entry_price.toFixed(3)}</td>
                    <td className="td text-right nums">{p.exit_price?.toFixed(2) ?? "—"}</td>
                    <td className={`td text-right nums font-medium ${win ? "text-up" : "text-down"}`}>
                      {signed(p.pnl)}
                    </td>
                    <td className="td text-right text-xs text-slate-500">{timeAgo(p.closed_at)}</td>
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
