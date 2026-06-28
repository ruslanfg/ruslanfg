import { useEffect, useRef, useState } from "react";
import { useDashboard } from "./hooks/useDashboard";
import { Header } from "./components/Header";
import { HeroBand } from "./components/HeroBand";
import { Disclaimer } from "./components/Disclaimer";
import { SourceHealth } from "./components/SourceHealth";
import { StatsBar } from "./components/StatsBar";
import { ValueBoard } from "./components/ValueBoard";
import { PowerRankings } from "./components/PowerRankings";
import { MatchCardView } from "./components/MatchCard";
import { SmartMoneyPanel } from "./components/SmartMoney";

const DEFAULT_DISCLAIMER =
  "Outputs are statistical model estimates and public betting-market data, shown for " +
  "information only. They are NOT betting advice, financial advice, or guaranteed outcomes.";

type Filter = "all" | "live" | "upcoming" | "finished";

export default function App() {
  const { data, conn, refreshing, forceRefresh } = useDashboard();
  const [filter, setFilter] = useState<Filter>("all");

  // Bump a tick whenever fresh data lands, to fire the hero ball's refresh pulse.
  const [refreshTick, setRefreshTick] = useState(0);
  const lastUpdated = useRef(0);
  useEffect(() => {
    if (data?.updated_at && data.updated_at !== lastUpdated.current) {
      lastUpdated.current = data.updated_at;
      setRefreshTick((t) => t + 1);
    }
  }, [data?.updated_at]);

  const matches = data?.matches ?? [];
  const live = matches.filter((m) => m.status === "live");
  const upcoming = matches.filter((m) => m.status === "upcoming" || m.status === "unknown");
  const finished = matches.filter((m) => m.status === "finished");
  const hasMatches = matches.length > 0;

  const show = (s: Filter) => filter === "all" || filter === s;

  return (
    <div className="min-h-full pb-24">
      <Header data={data} conn={conn} refreshing={refreshing} onRefresh={forceRefresh} />

      <HeroBand data={data} refreshTick={refreshTick} />

      <main className="mx-auto max-w-7xl px-4 py-4 sm:px-6">
        {data && data.sources.length > 0 && (
          <div className="mb-4">
            <SourceHealth sources={data.sources} />
          </div>
        )}

        {conn === "offline" && (
          <Banner tone="loss">
            Cannot reach the backend API. Is it running on the configured port?
          </Banner>
        )}

        {data && !hasMatches && conn !== "offline" && (
          <Banner tone="muted">
            No match data available yet. This is expected until the backend can reach the
            football data API (set <code className="text-slate-300">FOOTBALL_DATA_API_KEY</code> in{" "}
            <code className="text-slate-300">.env</code>) — sources above show live status. The
            dashboard never invents data.
          </Banner>
        )}

        {data && hasMatches && (
          <>
            {/* tournament-wide derived stats */}
            <div className="mb-5">
              <StatsBar stats={data.stats} />
            </div>

            {/* tournament insight row: value edges + Elo power rankings */}
            <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
              <ValueBoard rows={data.value_board} />
              <PowerRankings rows={data.power_rankings} />
            </div>
          </>
        )}

        {/* live matches + smart money */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2">
            {hasMatches && (
              <FilterTabs
                filter={filter}
                setFilter={setFilter}
                counts={{
                  all: matches.length,
                  live: live.length,
                  upcoming: upcoming.length,
                  finished: finished.length,
                }}
              />
            )}

            {show("live") && (
              <Section title="Live" count={live.length} accent>
                <CardGrid>
                  {live.map((m) => (
                    <MatchCardView key={m.id} m={m} />
                  ))}
                </CardGrid>
              </Section>
            )}

            {show("upcoming") && (
              <Section title="Upcoming" count={upcoming.length}>
                <CardGrid>
                  {upcoming.map((m) => (
                    <MatchCardView key={m.id} m={m} />
                  ))}
                </CardGrid>
              </Section>
            )}

            {show("finished") && (
              <Section title="Finished" count={finished.length}>
                <CardGrid>
                  {finished.map((m) => (
                    <MatchCardView key={m.id} m={m} />
                  ))}
                </CardGrid>
              </Section>
            )}
          </div>

          <aside className="lg:col-span-1">
            <div className="lg:sticky lg:top-20 space-y-4">
              {data && <SmartMoneyPanel data={data.smart_money} />}
              <Notes />
            </div>
          </aside>
        </div>
      </main>

      <Disclaimer text={data?.disclaimer || DEFAULT_DISCLAIMER} />
    </div>
  );
}

function FilterTabs({
  filter,
  setFilter,
  counts,
}: {
  filter: Filter;
  setFilter: (f: Filter) => void;
  counts: { all: number; live: number; upcoming: number; finished: number };
}) {
  const tabs: { key: Filter; label: string; n: number }[] = [
    { key: "all", label: "All", n: counts.all },
    { key: "live", label: "Live", n: counts.live },
    { key: "upcoming", label: "Upcoming", n: counts.upcoming },
    { key: "finished", label: "Finished", n: counts.finished },
  ];
  return (
    <div className="mb-4 inline-flex flex-wrap gap-1 rounded-xl border border-white/[0.07] bg-ink-850 p-1">
      {tabs.map((t) => (
        <button
          key={t.key}
          onClick={() => setFilter(t.key)}
          aria-pressed={filter === t.key}
          className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-medium transition-colors ${
            filter === t.key
              ? "bg-floodlight/15 text-floodlight"
              : "text-slate-400 hover:bg-white/[0.04] hover:text-slate-200"
          }`}
        >
          {t.label}
          <span className="numeric text-[10px] text-slate-500">{t.n}</span>
        </button>
      ))}
    </div>
  );
}

function Section({
  title,
  count,
  accent,
  children,
}: {
  title: string;
  count: number;
  accent?: boolean;
  children: React.ReactNode;
}) {
  if (count === 0) return null;
  return (
    <section className="mb-6">
      <div className="mb-1 flex items-center gap-2">
        <h2 className="font-display text-[13px] font-semibold uppercase tracking-[0.14em] text-slate-200">
          {title}
        </h2>
        <span
          className={`chip numeric ${accent ? "bg-loss/15 text-loss" : "bg-ink-700 text-slate-400"}`}
        >
          {count}
        </span>
      </div>
      <span className="seg-tick mb-3 animate-underline-draw" />
      {children}
    </section>
  );
}

function CardGrid({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-1 gap-4 md:grid-cols-2">{children}</div>;
}

function Banner({ tone, children }: { tone: "loss" | "muted"; children: React.ReactNode }) {
  const cls =
    tone === "loss"
      ? "border-loss/20 bg-loss/[0.06] text-loss"
      : "border-white/[0.06] bg-ink-850/60 text-slate-400";
  return (
    <div className={`mb-4 rounded-xl border px-4 py-3 text-[12.5px] leading-relaxed ${cls}`}>
      {children}
    </div>
  );
}

function Notes() {
  return (
    <div className="rounded-2xl border border-white/[0.05] bg-ink-900/40 p-4 text-[11px] leading-relaxed text-slate-500">
      <div className="label mb-1.5">How to read this</div>
      <ul className="space-y-1.5">
        <li>
          <span className="text-win">Model</span> = win/draw/loss from Elo (built from real
          results) + recent form, plus live score &amp; minute when in play.
        </li>
        <li>
          <span className="text-slate-300">Book</span> = sportsbook implied probability (vig
          removed). <span className="text-slate-300">Poly</span> = Polymarket price.
        </li>
        <li>
          A green <span className="text-win">value</span> row means the model assigns more
          probability than the book — an informational edge signal, not advice.
        </li>
        <li>
          Ratings marked <span className="text-amber-300">*</span> are provisional (few matches
          played) → wider bands.
        </li>
      </ul>
    </div>
  );
}
