import { useEffect, useState } from "react";
import { useLiveState } from "./hooks/useLiveState";
import { api, ClosedPosition, EquityPoint, OpenPosition, Wallet } from "./api";
import Header from "./components/Header";
import Hero from "./components/Hero";
import EquityCurve from "./components/EquityCurve";
import MarketCard from "./components/MarketCard";
import WalletLeaderboard from "./components/WalletLeaderboard";
import { ClosedTrades, OpenPositions } from "./components/Tables";

export default function App() {
  const { snapshot, conn } = useLiveState();
  const [open, setOpen] = useState<OpenPosition[]>([]);
  const [closed, setClosed] = useState<ClosedPosition[]>([]);
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [equity, setEquity] = useState<EquityPoint[]>([]);

  // Poll the list endpoints (the WS carries the headline snapshot; tables
  // refresh on a short interval and immediately whenever a snapshot lands).
  useEffect(() => {
    let alive = true;
    const pull = () => {
      api.openPositions().then((d) => alive && setOpen(d)).catch(() => {});
      api.closedPositions(100).then((d) => alive && setClosed(d)).catch(() => {});
      api.wallets().then((d) => alive && setWallets(d)).catch(() => {});
      api.equityCurve().then((d) => alive && setEquity(d)).catch(() => {});
    };
    pull();
    const id = setInterval(pull, 3000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  // Refresh tables promptly when the snapshot changes (e.g. a settlement).
  useEffect(() => {
    if (!snapshot) return;
    api.openPositions().then(setOpen).catch(() => {});
    api.equityCurve().then(setEquity).catch(() => {});
  }, [snapshot?.updated_at, snapshot?.stats.closed_trades]);

  const starting = snapshot?.bankroll.starting ?? 1000;

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 md:px-8 md:py-8 space-y-6">
      <Header conn={conn} mode={snapshot?.mode} updatedAt={snapshot?.updated_at} />

      <Hero snap={snapshot} />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <EquityCurve data={equity} starting={starting} />
        </div>
        <MarketCard market={snapshot?.market ?? null} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <OpenPositions rows={open} />
        <WalletLeaderboard wallets={wallets} />
      </div>

      <ClosedTrades rows={closed} />

      <footer className="pt-2 pb-6 text-center text-xs text-slate-600">
        Paper trading only · no wallet keys · no real funds · fills simulated against live prices.
      </footer>
    </div>
  );
}
