// REST client + types for the World Cup dashboard backend.
// Same-origin relative URLs; Vite proxies /api to the FastAPI backend in dev.

export interface SourceStatus {
  name: string;
  label: string;
  ok: boolean;
  detail: string | null;
  last_ok_at: number | null;
  checked_at: number | null;
}

export interface TeamRef {
  id: string | null;
  name: string;
  crest: string | null;
  elo: number | null;
  elo_provisional: boolean;
  form: string[] | null;
  form_ppg: number | null;
}

export interface Factor {
  label: string;
  detail: string;
}

export interface ModelEstimate {
  home_win: number;
  draw: number;
  away_win: number;
  band: number;
  provisional: boolean;
  basis: "pre-match" | "in-match";
  expected_goals: { home: number; away: number };
  factors: Factor[];
  note: string;
}

export interface ValueFlag {
  edge: number | null;
  flagged: boolean;
}

export interface OutcomeRow {
  key: "home" | "draw" | "away";
  label: string;
  model_pct: number | null;
  sportsbook_pct: number | null;
  polymarket_pct: number | null;
  value: ValueFlag;
}

export interface MarketComparison {
  outcomes: OutcomeRow[];
  sportsbook_available: boolean;
  sportsbook_book: string | null;
  polymarket_available: boolean;
  polymarket_slug: string | null;
  note: string | null;
}

export interface Lineups {
  home: string[];
  away: string[];
  formation_home: string | null;
  formation_away: string | null;
}

export interface MatchCard {
  id: string;
  status: "upcoming" | "live" | "finished" | "unknown";
  utc_date: string | null;
  minute: number | null;
  minute_approx: boolean;
  stage: string | null;
  group: string | null;
  home: TeamRef;
  away: TeamRef;
  score: { home: number | null; away: number | null };
  model: ModelEstimate | null;
  market: MarketComparison | null;
  lineups_available: boolean;
  lineups: Lineups | null;
  data_note: string | null;
}

export interface TraderPosition {
  market_title: string;
  slug: string | null;
  outcome: string | null;
  size: number | null;
  avg_price: number | null;
  cur_price: number | null;
  value_usd: number | null;
  unrealized_pnl: number | null;
}

export interface Trader {
  rank: number | null;
  address: string;
  display: string | null;
  pnl: number | null;
  volume: number | null;
  positions: TraderPosition[] | null;
  positions_note: string | null;
}

export interface SmartMoney {
  available: boolean;
  note: string | null;
  leaderboard: Trader[];
}

export interface Dashboard {
  updated_at: number;
  disclaimer: string;
  tournament: { name: string; hosts: string; window: string };
  sources: SourceStatus[];
  matches: MatchCard[];
  smart_money: SmartMoney;
  live_count: number;
  value_count: number;
}

async function j<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json();
}

export const api = {
  dashboard: () => j<Dashboard>("/api/dashboard"),
  refresh: async () => {
    const r = await fetch("/api/refresh", { method: "POST" });
    if (!r.ok) throw new Error(`refresh -> ${r.status}`);
    return r.json();
  },
};
