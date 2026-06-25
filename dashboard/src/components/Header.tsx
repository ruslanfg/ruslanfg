import { ConnState } from "../hooks/useLiveState";

const dot = (c: string) => (
  <span className={`inline-block h-2 w-2 rounded-full ${c}`} />
);

export default function Header({
  conn,
  mode,
  updatedAt,
}: {
  conn: ConnState;
  mode: string | undefined;
  updatedAt: number | undefined;
}) {
  const connMeta =
    conn === "live"
      ? { c: "bg-up animate-pulse-dot", t: "Live" }
      : conn === "connecting"
      ? { c: "bg-amber-400 animate-pulse-dot", t: "Connecting" }
      : { c: "bg-down", t: "Offline" };

  return (
    <header className="flex items-center justify-between gap-4 flex-wrap">
      <div className="flex items-center gap-3">
        <div className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-accent/30 to-up/20 border border-white/10 text-lg font-bold">
          ₿
        </div>
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-slate-100">
            BTC 5‑Minute · Paper Copy Bot
          </h1>
          <p className="text-xs text-slate-500">
            Polymarket · mirrors top wallets · simulated fills · no real funds
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        {mode && (
          <span className="rounded-full border border-white/10 bg-ink-800/60 px-3 py-1 text-xs text-slate-400">
            data: <span className="text-slate-200 font-medium">{mode}</span>
          </span>
        )}
        <span className="flex items-center gap-2 rounded-full border border-white/10 bg-ink-800/60 px-3 py-1 text-xs text-slate-300">
          {dot(connMeta.c)} {connMeta.t}
        </span>
      </div>
    </header>
  );
}
