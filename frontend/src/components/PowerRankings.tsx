import { PowerRankingRow } from "../api";

const FORM_COLOR: Record<string, string> = {
  W: "bg-win/20 text-win",
  D: "bg-draw/20 text-draw",
  L: "bg-loss/20 text-loss",
};

function MiniForm({ form }: { form: string[] | null }) {
  if (!form || form.length === 0) return null;
  return (
    <div className="flex gap-0.5">
      {form.slice(-5).map((r, i) => (
        <span
          key={i}
          className={`flex h-3.5 w-3.5 items-center justify-center rounded-[2px] text-[8px] font-bold ${
            FORM_COLOR[r] || "bg-ink-700 text-slate-400"
          }`}
        >
          {r}
        </span>
      ))}
    </div>
  );
}

// Elo power rankings — teams ranked by ratings the model built from real
// results. The bar is each team's Elo relative to the field.
export function PowerRankings({ rows }: { rows: PowerRankingRow[] }) {
  return (
    <div className="card overflow-hidden">
      <div className="chrome-glass flex items-center justify-between border-b border-white/[0.06] px-4 py-3">
        <h2 className="font-display text-sm font-semibold uppercase tracking-[0.08em] text-slate-100">
          Power rankings
        </h2>
        <span className="label">Live Elo</span>
      </div>

      {rows.length === 0 ? (
        <div className="p-4 text-[12px] text-slate-500">
          Rankings appear once match results are available — built from real games, not
          assumed.
        </div>
      ) : (
        <div className="max-h-[460px] overflow-y-auto px-2 py-2">
          {(() => {
            const elos = rows.map((r) => r.elo);
            const max = Math.max(...elos);
            const min = Math.min(...elos);
            const span = Math.max(1, max - min);
            return rows.map((r) => {
              const pctWidth = 22 + ((r.elo - min) / span) * 78; // 22%..100%
              return (
                <div
                  key={r.team_id ?? r.name}
                  className="group relative flex items-center gap-2.5 rounded-lg px-2 py-1.5 hover:bg-white/[0.03]"
                >
                  <span className="numeric w-5 shrink-0 text-right text-[11px] text-slate-500">
                    {r.rank}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-[13px] font-medium text-slate-100">
                        {r.name}
                        {r.provisional && (
                          <span className="ml-1 text-amber-300/80" title="Provisional (few matches)">
                            *
                          </span>
                        )}
                      </span>
                      <span className="numeric shrink-0 text-[12px] text-slate-300">
                        {Math.round(r.elo)}
                      </span>
                    </div>
                    <div className="mt-1 flex items-center gap-2">
                      <div className="h-1 flex-1 overflow-hidden rounded-full bg-ink-700">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-accent/70 to-win/80 transition-[width] duration-500"
                          style={{ width: `${pctWidth}%` }}
                        />
                      </div>
                      <MiniForm form={r.form} />
                    </div>
                  </div>
                </div>
              );
            });
          })()}
        </div>
      )}
    </div>
  );
}
