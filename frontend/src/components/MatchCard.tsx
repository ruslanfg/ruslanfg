import { useState } from "react";
import { MatchCard as Match, TeamRef } from "../api";
import { kickoff } from "../lib/format";
import { ProbabilityBar } from "./ProbabilityBar";
import { MarketTable } from "./MarketTable";

function Crest({ team }: { team: TeamRef }) {
  const [broken, setBroken] = useState(false);
  if (team.crest && !broken) {
    return (
      <img
        src={team.crest}
        alt=""
        className="h-7 w-7 shrink-0 object-contain"
        onError={() => setBroken(true)}
      />
    );
  }
  const initials = team.name.slice(0, 3).toUpperCase();
  return (
    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-ink-700 text-[9px] font-semibold text-slate-400">
      {initials}
    </div>
  );
}

function Form({ form }: { form: string[] | null }) {
  if (!form || form.length === 0) return null;
  const color: Record<string, string> = {
    W: "bg-win/20 text-win",
    D: "bg-draw/20 text-draw",
    L: "bg-loss/20 text-loss",
  };
  return (
    <div className="flex gap-1">
      {form.map((r, i) => (
        <span
          key={i}
          className={`flex h-4 w-4 items-center justify-center rounded text-[9px] font-bold ${
            color[r] || "bg-ink-700 text-slate-400"
          }`}
        >
          {r}
        </span>
      ))}
    </div>
  );
}

function StatusBadge({ m }: { m: Match }) {
  if (m.status === "live") {
    return (
      <span className="chip bg-loss/15 text-loss">
        <span className="h-1.5 w-1.5 rounded-full bg-loss animate-pulse-dot" />
        LIVE {m.minute ? `~${m.minute}'` : ""}
      </span>
    );
  }
  if (m.status === "finished") return <span className="chip bg-ink-700 text-slate-400">FT</span>;
  if (m.status === "upcoming")
    return <span className="chip bg-accent/10 text-accent">{kickoff(m.utc_date)}</span>;
  return <span className="chip bg-ink-700 text-slate-500">scheduled</span>;
}

function TeamLine({ team, goals }: { team: TeamRef; goals: number | null }) {
  return (
    <div className="flex items-center gap-2.5">
      <Crest team={team} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate font-medium text-slate-100">{team.name}</span>
          {team.elo !== null && (
            <span
              className="shrink-0 text-[10px] text-slate-500 nums"
              title={team.elo_provisional ? "Provisional rating (few matches played)" : "Elo rating"}
            >
              {Math.round(team.elo)}
              {team.elo_provisional ? "*" : ""}
            </span>
          )}
        </div>
        <Form form={team.form} />
      </div>
      {goals !== null && <div className="text-2xl font-bold text-slate-100 nums">{goals}</div>}
    </div>
  );
}

export function MatchCardView({ m }: { m: Match }) {
  const [showWhy, setShowWhy] = useState(false);
  const [showXI, setShowXI] = useState(false);
  const showScore = m.status === "live" || m.status === "finished";

  return (
    <div className="card animate-fade-in flex flex-col p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="label truncate">
          {m.stage ? m.stage.replace(/_/g, " ") : "Match"}
          {m.group ? ` · ${m.group.replace("GROUP_", "Grp ")}` : ""}
        </div>
        <StatusBadge m={m} />
      </div>

      <div className="space-y-2.5">
        <TeamLine team={m.home} goals={showScore ? m.score.home : null} />
        <TeamLine team={m.away} goals={showScore ? m.score.away : null} />
      </div>

      <div className="mt-4">
        {m.model ? (
          <ProbabilityBar model={m.model} homeName={m.home.name} awayName={m.away.name} />
        ) : (
          <div className="rounded-lg bg-ink-800/60 px-3 py-2 text-[12px] text-slate-500">
            Model estimate unavailable — not enough rating data yet.
          </div>
        )}
      </div>

      {m.model && m.model.factors.length > 0 && (
        <div className="mt-2">
          <button
            onClick={() => setShowWhy((v) => !v)}
            className="text-[11px] text-accent/90 hover:text-accent"
          >
            {showWhy ? "Hide" : "Why these numbers?"}
          </button>
          {showWhy && (
            <ul className="mt-1.5 space-y-1">
              {m.model.factors.map((f, i) => (
                <li key={i} className="text-[11.5px] text-slate-400">
                  <span className="text-slate-300">{f.label}:</span> {f.detail}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {m.market && (
        <div className="mt-3">
          <MarketTable market={m.market} />
        </div>
      )}

      {m.lineups_available && m.lineups && (
        <div className="mt-3">
          <button
            onClick={() => setShowXI((v) => !v)}
            className="text-[11px] text-accent/90 hover:text-accent"
          >
            {showXI ? "Hide lineups" : "Lineups"}
          </button>
          {showXI && (
            <div className="mt-2 grid grid-cols-2 gap-3 text-[11px] text-slate-400">
              {[
                { team: m.home.name, xi: m.lineups.home, f: m.lineups.formation_home },
                { team: m.away.name, xi: m.lineups.away, f: m.lineups.formation_away },
              ].map((side) => (
                <div key={side.team}>
                  <div className="mb-1 font-medium text-slate-300">
                    {side.team} {side.f ? <span className="text-slate-500">{side.f}</span> : null}
                  </div>
                  <ol className="space-y-0.5">
                    {side.xi.map((p, i) => (
                      <li key={i} className="truncate">
                        {p}
                      </li>
                    ))}
                  </ol>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
