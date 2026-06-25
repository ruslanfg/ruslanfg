import { useState } from "react";
import { Snapshot, api } from "../api";
import AnimatedNumber from "./AnimatedNumber";
import { pct, signed, pos } from "../lib/format";

export default function Hero({ snap }: { snap: Snapshot | null }) {
  const [busy, setBusy] = useState(false);
  const [enabled, setEnabled] = useState<boolean | null>(null);

  const on = enabled ?? snap?.enabled ?? false;
  const b = snap?.bankroll;
  const realized = b?.realized_pnl ?? 0;
  const ret = b?.return_pct ?? 0;
  const up = pos(realized);

  const toggle = async () => {
    setBusy(true);
    try {
      const r = await api.toggle(!on);
      setEnabled(r.enabled);
    } catch {
      /* ignore */
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card card-pad animate-fade-in relative overflow-hidden">
      <div className="pointer-events-none absolute -right-16 -top-20 h-56 w-56 rounded-full bg-accent/10 blur-3xl" />
      <div className="flex items-start justify-between gap-6 flex-wrap">
        <div>
          <div className="label">Paper bankroll · equity</div>
          <div className="mt-1 flex items-end gap-3">
            <AnimatedNumber
              value={b?.equity ?? 0}
              prefix="$"
              className="text-5xl md:text-6xl font-extrabold tracking-tight text-white"
            />
            <span
              className={`mb-2 rounded-md px-2 py-0.5 text-sm font-semibold ${
                up ? "bg-up/10 text-up" : "bg-down/10 text-down"
              }`}
            >
              {signed(ret, 2)}%
            </span>
          </div>
          <div className="mt-2 text-sm text-slate-400">
            Realized PnL{" "}
            <span className={`font-semibold ${up ? "text-up" : "text-down"} nums`}>
              {signed(realized)}
            </span>{" "}
            · started ${b?.starting?.toLocaleString() ?? "—"}
          </div>
        </div>

        <div className="flex flex-col items-end gap-3">
          <span
            className={`flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium ${
              on ? "bg-up/10 text-up" : "bg-slate-500/10 text-slate-400"
            }`}
          >
            <span
              className={`h-2 w-2 rounded-full ${on ? "bg-up animate-pulse-dot" : "bg-slate-500"}`}
            />
            {on ? "Bot running" : "Bot paused"}
          </span>
          <button
            onClick={toggle}
            disabled={busy}
            className={`rounded-xl px-5 py-2.5 text-sm font-semibold transition-all duration-200 disabled:opacity-50 ${
              on
                ? "bg-down/15 text-down hover:bg-down/25 border border-down/20"
                : "bg-up/15 text-up hover:bg-up/25 border border-up/20"
            }`}
          >
            {busy ? "…" : on ? "Stop bot" : "Start bot"}
          </button>
        </div>
      </div>

      <div className="mt-6 grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Mini label="Cash" value={b?.cash ?? 0} prefix="$" />
        <Mini label="Open exposure" value={b?.open_exposure ?? 0} prefix="$" />
        <Mini label="Open positions" value={snap?.open_positions ?? 0} decimals={0} />
        <Mini
          label="Win rate"
          raw={pct(snap?.stats.win_rate ?? 0)}
          sub={`${snap?.stats.wins ?? 0}W / ${snap?.stats.losses ?? 0}L`}
        />
      </div>
    </div>
  );
}

function Mini({
  label,
  value,
  prefix,
  decimals = 2,
  raw,
  sub,
}: {
  label: string;
  value?: number;
  prefix?: string;
  decimals?: number;
  raw?: string;
  sub?: string;
}) {
  return (
    <div className="rounded-xl bg-ink-800/50 border border-white/[0.05] px-4 py-3">
      <div className="label">{label}</div>
      <div className="mt-1 text-lg font-semibold text-slate-100">
        {raw !== undefined ? (
          <span className="nums">{raw}</span>
        ) : (
          <AnimatedNumber value={value ?? 0} prefix={prefix} decimals={decimals} />
        )}
      </div>
      {sub && <div className="text-[11px] text-slate-500 mt-0.5">{sub}</div>}
    </div>
  );
}
