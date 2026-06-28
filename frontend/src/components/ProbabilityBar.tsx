import { ModelEstimate } from "../api";
import { pct } from "../lib/format";

// Stacked Home / Draw / Away probability bar for the model's point estimate,
// with a glossy finish, a soft same-color confidence wash, and the verbatim
// "not a guarantee" label. Semantics stay quarantined to the bar.
export function ProbabilityBar({
  model,
  homeName,
  awayName,
}: {
  model: ModelEstimate;
  homeName: string;
  awayName: string;
}) {
  const segs = [
    { label: homeName, value: model.home_win, bar: "bg-win", text: "text-win", glow: "rgba(52,211,153,0.35)" },
    { label: "Draw", value: model.draw, bar: "bg-draw", text: "text-draw", glow: "rgba(251,191,36,0.32)" },
    { label: awayName, value: model.away_win, bar: "bg-loss", text: "text-loss", glow: "rgba(251,113,133,0.35)" },
  ];
  // soft same-color wash behind the bar conveys the confidence band visually
  const dominant = segs.reduce((a, b) => (b.value > a.value ? b : a));
  return (
    <div>
      <div className="relative">
        <div
          className="absolute -inset-x-1 -bottom-1 top-0 rounded-full opacity-60 blur-[6px]"
          style={{ background: `linear-gradient(90deg, transparent, ${dominant.glow}, transparent)` }}
          aria-hidden
        />
        <div className="relative flex h-3 w-full overflow-hidden rounded-full bg-ink-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]">
          {segs.map((s) => (
            <div
              key={s.label}
              className={`relative ${s.bar}`}
              style={{ width: `${Math.max(0, s.value * 100)}%` }}
              title={`${s.label}: ${pct(s.value)}`}
            >
              <span className="absolute inset-x-0 top-0 h-1/2 bg-white/15" />
            </div>
          ))}
        </div>
      </div>

      <div className="mt-2 grid grid-cols-3 gap-1">
        {segs.map((s) => (
          <div key={s.label} className="min-w-0">
            <div className={`numeric text-[15px] font-semibold ${s.text}`}>{pct(s.value)}</div>
            <div className="truncate text-[11px] text-slate-400">{s.label}</div>
          </div>
        ))}
      </div>

      <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-slate-500">
        <span className="text-slate-400">Model estimate, not a guarantee.</span>
        <span>
          · confidence band <span className="numeric">±{Math.round(model.band * 100)}%</span>
        </span>
        <span>· {model.basis}</span>
        {model.provisional && (
          <span className="chip bg-amber-500/10 text-amber-300/90">provisional ratings</span>
        )}
      </div>
    </div>
  );
}
