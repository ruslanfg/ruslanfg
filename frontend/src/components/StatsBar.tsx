import { TournamentStats } from "../api";
import { DASH, signedPct } from "../lib/format";

function Tile({
  label,
  value,
  sub,
  valueClass = "text-slate-100",
  display,
}: {
  label: string;
  value: string;
  sub?: string;
  valueClass?: string;
  display?: boolean;
}) {
  return (
    <div className="card card-hover p-3.5">
      <div className="label text-[9.5px] text-slate-500">{label}</div>
      <div
        className={`mt-0.5 truncate text-xl font-semibold ${display ? "font-display" : "numeric"} ${valueClass}`}
        title={value}
      >
        {value}
      </div>
      {sub && <div className="mt-0.5 truncate text-[10.5px] text-slate-500">{sub}</div>}
    </div>
  );
}

// Tournament-wide metric tiles — every figure is DERIVED from fetched data
// (Elo, goals, edges); nothing is invented. Missing data shows an em dash.
export function StatsBar({ stats }: { stats: TournamentStats }) {
  const s = stats;
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      <Tile
        label="Matches"
        value={String(s.matches_total)}
        sub={`${s.live} live · ${s.finished} FT`}
      />
      <Tile
        label="Goals scored"
        value={s.goals_total === null ? DASH : String(s.goals_total)}
        sub={s.finished ? `in ${s.finished} matches` : "no results yet"}
      />
      <Tile
        label="Avg / match"
        value={s.avg_goals === null ? DASH : s.avg_goals.toFixed(2)}
        sub="goals per game"
      />
      <Tile label="Teams ranked" value={String(s.teams_ranked)} sub="by live Elo" />
      <Tile
        label="Top side"
        display
        value={s.top_team || DASH}
        sub={s.top_team_elo ? `Elo ${s.top_team_elo}` : "—"}
      />
      <Tile
        label="Best edge"
        value={s.biggest_edge === null ? DASH : signedPct(s.biggest_edge)}
        valueClass={s.biggest_edge && s.biggest_edge > 0 ? "text-win" : "text-slate-100"}
        sub={`${s.value_count} value flags`}
      />
    </div>
  );
}
