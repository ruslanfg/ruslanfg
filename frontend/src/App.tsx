import { useDashboard } from "./hooks/useDashboard";
import { Header } from "./components/Header";
import { Disclaimer } from "./components/Disclaimer";
import { SourceHealth } from "./components/SourceHealth";
import { MatchCardView } from "./components/MatchCard";
import { SmartMoneyPanel } from "./components/SmartMoney";

const DEFAULT_DISCLAIMER =
  "Outputs are statistical model estimates and public betting-market data, shown for " +
  "information only. They are NOT betting advice, financial advice, or guaranteed outcomes.";

export default function App() {
  const { data, conn, refreshing, forceRefresh } = useDashboard();

  const matches = data?.matches ?? [];
  const live = matches.filter((m) => m.status === "live");
  const upcoming = matches.filter((m) => m.status === "upcoming" || m.status === "unknown");
  const finished = matches.filter((m) => m.status === "finished");

  return (
    <div className="min-h-full pb-12">
      <Header data={data} conn={conn} refreshing={refreshing} onRefresh={forceRefresh} />

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

        {data && matches.length === 0 && conn !== "offline" && (
          <Banner tone="muted">
            No match data available yet. This is expected until the backend can reach the
            football data API (set <code className="text-slate-300">FOOTBALL_DATA_API_KEY</code> in{" "}
            <code className="text-slate-300">.env</code>) — sources above show live status. The
            dashboard never invents data.
          </Banner>
        )}

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <Section title="Live" count={live.length} accent>
              <CardGrid>
                {live.map((m) => (
                  <MatchCardView key={m.id} m={m} />
                ))}
              </CardGrid>
            </Section>

            <Section title="Upcoming" count={upcoming.length}>
              <CardGrid>
                {upcoming.map((m) => (
                  <MatchCardView key={m.id} m={m} />
                ))}
              </CardGrid>
            </Section>

            <Section title="Finished" count={finished.length}>
              <CardGrid>
                {finished.map((m) => (
                  <MatchCardView key={m.id} m={m} />
                ))}
              </CardGrid>
            </Section>
          </div>

          <aside className="lg:col-span-1">
            <div className="lg:sticky lg:top-20">
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
      <div className="mb-2 flex items-center gap-2">
        <h2 className="text-sm font-semibold text-slate-200">{title}</h2>
        <span
          className={`chip ${accent ? "bg-loss/15 text-loss" : "bg-ink-700 text-slate-400"}`}
        >
          {count}
        </span>
      </div>
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
    <div className="mt-4 rounded-2xl border border-white/[0.05] bg-ink-900/40 p-4 text-[11px] leading-relaxed text-slate-500">
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
        <li>Ratings marked <span className="text-amber-300">*</span> are provisional (few matches played) → wider bands.</li>
      </ul>
    </div>
  );
}
