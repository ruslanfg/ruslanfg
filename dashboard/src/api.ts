// REST + WebSocket client for the paper-trading backend.
// Uses same-origin relative URLs (Vite proxies /api and /ws to the backend).

export interface Snapshot {
  type: string;
  updated_at: number;
  mode: string;
  enabled: boolean;
  open_positions: number;
  bankroll: {
    starting: number;
    cash: number;
    equity: number;
    realized_pnl: number;
    open_exposure: number;
    return_pct: number;
  };
  stats: { closed_trades: number; wins: number; losses: number; win_rate: number };
  market: MarketState | null;
}

export interface Quote { bid: number | null; ask: number | null; mid: number | null }

export interface MarketState {
  condition_id: string;
  question: string;
  slug: string;
  start_time: number;
  end_time: number;
  seconds_left: number;
  active: boolean;
  closed: boolean;
  resolved_outcome: string | null;
  up: Quote | null;
  down: Quote | null;
  source: string;
}

export interface OpenPosition {
  id: number;
  condition_id: string;
  market_question: string;
  source_wallet: string;
  outcome: string;
  entry_price: number;
  shares: number;
  size_usd: number;
  opened_at: number;
  market_end_time: number;
  current_price: number;
  current_value: number;
  unrealized_pnl: number;
}

export interface ClosedPosition {
  id: number;
  condition_id: string;
  source_wallet: string;
  outcome: string;
  resolved_outcome: string | null;
  entry_price: number;
  exit_price: number | null;
  shares: number;
  size_usd: number;
  pnl: number | null;
  opened_at: number;
  closed_at: number | null;
}

export interface Wallet {
  wallet: string;
  rank: number | null;
  win_rate: number;
  realized_pnl: number;
  volume: number;
  trades_count: number;
  score: number;
}

export interface EquityPoint {
  timestamp: number;
  equity: number;
  bankroll: number;
  realized_pnl: number;
  open_positions: number;
}

const j = async <T>(path: string): Promise<T> => {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return r.json();
};

export const api = {
  state: () => j<Snapshot>("/api/state"),
  openPositions: () => j<OpenPosition[]>("/api/positions/open"),
  closedPositions: (limit = 100) => j<ClosedPosition[]>(`/api/positions/closed?limit=${limit}`),
  wallets: () => j<Wallet[]>("/api/wallets"),
  equityCurve: (limit = 1000) => j<EquityPoint[]>(`/api/equity-curve?limit=${limit}`),
  toggle: async (enabled: boolean) => {
    const r = await fetch("/api/bot/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    });
    if (!r.ok) throw new Error(`toggle → ${r.status}`);
    return r.json() as Promise<{ enabled: boolean }>;
  },
};

export function wsUrl(): string {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/ws`;
}
