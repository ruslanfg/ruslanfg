import { ModelEstimate } from "../api";
import { pct } from "../lib/format";

// Stacked Home / Draw / Away probability bar for the model's point estimate,
// with an explicit confidence band and a "not a guarantee" label.
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
    { label: homeName, value: model.home_win, color: "bg-win", text: "text-win" },
    { label: "Draw", value: model.draw, color: "bg-draw", text: "text-draw" },
    { label: awayName, value: model.away_win, color: "bg-loss", text: "text-loss" },
  ];
  return (
    <div>
      <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-ink-700">
        {segs.map((s) => (
          <div
            key={s.label}
            className={s.color}
            style={{ width: `${Math.max(0, s.value * 100)}%` }}
            title={`${s.label}: ${pct(s.value)}`}
          />
        ))}
      </div>
      <div className="mt-2 grid grid-cols-3 gap-1 nums">
        {segs.map((s) => (
          <div key={s.label} className="min-w-0">
            <div className={`text-sm font-semibold ${s.text}`}>{pct(s.value)}</div>
            <div className="truncate text-[11px] text-slate-400">{s.label}</div>
          </div>
        ))}
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-slate-500">
        <span className="text-slate-400">Model estimate, not a guarantee.</span>
        <span>· confidence band ±{Math.round(model.band * 100)}%</span>
        <span>· {model.basis}</span>
        {model.provisional && (
          <span className="chip bg-amber-500/10 text-amber-300/90">provisional ratings</span>
        )}
      </div>
    </div>
  );
}
