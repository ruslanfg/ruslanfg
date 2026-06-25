import { useEffect, useState } from "react";
import { MarketState } from "../api";
import { mmss } from "../lib/format";

function OutcomeBar({ up, down }: { up: number; down: number }) {
  const total = up + down || 1;
  const upPct = (up / total) * 100;
  return (
    <div className="mt-3">
      <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-ink-700">
        <div className="bg-up/80 transition-all duration-500" style={{ width: `${upPct}%` }} />
        <div className="bg-down/80 transition-all duration-500" style={{ width: `${100 - upPct}%` }} />
      </div>
    </div>
  );
}

export default function MarketCard({ market }: { market: MarketState | null }) {
  // local countdown ticking between snapshots
  const [left, setLeft] = useState(market?.seconds_left ?? 0);
  useEffect(() => setLeft(market?.seconds_left ?? 0), [market?.seconds_left, market?.condition_id]);
  useEffect(() => {
    const id = setInterval(() => setLeft((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(id);
  }, []);

  if (!market) {
    return (
      <div className="card card-pad grid place-items-center h-full text-sm text-slate-600">
        No active market yet…
      </div>
    );
  }

  const upMid = market.up?.mid ?? 0.5;
  const downMid = market.down?.mid ?? 1 - upMid;
  const resolved = market.resolved_outcome;

  return (
    <div className="card card-pad animate-fade-in">
      <div className="flex items-center justify-between">
        <div className="label">Live market</div>
        {resolved ? (
          <span
            className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
              resolved === "UP" ? "bg-up/15 text-up" : "bg-down/15 text-down"
            }`}
          >
            resolved {resolved}
          </span>
        ) : (
          <span className="flex items-center gap-1.5 rounded-full bg-ink-800/70 px-2.5 py-0.5 text-xs text-slate-300 nums">
            <span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse-dot" />
            {mmss(left)}
          </span>
        )}
      </div>

      <div className="mt-1 font-mono text-xs text-slate-500 truncate" title={market.condition_id}>
        {market.slug || market.condition_id}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3">
        <Outcome label="UP" mid={upMid} q={market.up} color="up" />
        <Outcome label="DOWN" mid={downMid} q={market.down} color="down" />
      </div>
      <OutcomeBar up={upMid} down={downMid} />
      <div className="mt-2 flex justify-between text-[11px] text-slate-500">
        <span>UP {(upMid * 100).toFixed(0)}%</span>
        <span>DOWN {(downMid * 100).toFixed(0)}%</span>
      </div>
    </div>
  );
}

function Outcome({
  label,
  mid,
  q,
  color,
}: {
  label: string;
  mid: number;
  q: { bid: number | null; ask: number | null } | null;
  color: "up" | "down";
}) {
  return (
    <div className={`rounded-xl border px-4 py-3 ${color === "up" ? "border-up/20 bg-up/[0.04]" : "border-down/20 bg-down/[0.04]"}`}>
      <div className={`text-xs font-semibold ${color === "up" ? "text-up" : "text-down"}`}>{label}</div>
      <div className="mt-1 text-2xl font-bold text-slate-100 nums">{mid.toFixed(3)}</div>
      <div className="mt-0.5 text-[11px] text-slate-500 nums">
        bid {q?.bid?.toFixed(3) ?? "—"} · ask {q?.ask?.toFixed(3) ?? "—"}
      </div>
    </div>
  );
}
