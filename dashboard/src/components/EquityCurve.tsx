import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  ReferenceLine,
  CartesianGrid,
} from "recharts";
import { EquityPoint } from "../api";
import { usd } from "../lib/format";

export default function EquityCurve({
  data,
  starting,
}: {
  data: EquityPoint[];
  starting: number;
}) {
  const points = data.map((d) => ({
    t: d.timestamp * 1000,
    equity: d.equity,
    realized: d.realized_pnl,
  }));
  const last = points[points.length - 1]?.equity ?? starting;
  const up = last >= starting;
  const stroke = up ? "#34d399" : "#fb7185";

  const ys = points.map((p) => p.equity).concat(starting);
  const min = Math.min(...ys);
  const max = Math.max(...ys);
  const pad = Math.max((max - min) * 0.15, 5);

  return (
    <div className="card card-pad h-full animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <div className="label">Equity curve</div>
          <div className="text-sm text-slate-400 mt-0.5">
            Realized PnL over time · {points.length} points
          </div>
        </div>
        <div className={`text-sm font-semibold ${up ? "text-up" : "text-down"}`}>
          {usd(last)}
        </div>
      </div>
      <div className="mt-4 h-64">
        {points.length < 2 ? (
          <div className="grid h-full place-items-center text-sm text-slate-600">
            Waiting for equity history…
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: 4 }}>
              <defs>
                <linearGradient id="eq" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={stroke} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={stroke} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" vertical={false} />
              <XAxis
                dataKey="t"
                type="number"
                domain={["dataMin", "dataMax"]}
                tickFormatter={(t) =>
                  new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
                }
                tick={{ fontSize: 11, fill: "#64748b" }}
                stroke="rgba(255,255,255,0.06)"
                minTickGap={40}
              />
              <YAxis
                domain={[min - pad, max + pad]}
                tickFormatter={(v) => `$${Math.round(v)}`}
                tick={{ fontSize: 11, fill: "#64748b" }}
                stroke="rgba(255,255,255,0.06)"
                width={56}
              />
              <Tooltip
                contentStyle={{
                  background: "#0e1116",
                  border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 12,
                  fontSize: 12,
                }}
                labelFormatter={(t) => new Date(t as number).toLocaleString()}
                formatter={(v: number, name) => [usd(v), name === "equity" ? "Equity" : name]}
              />
              <ReferenceLine
                y={starting}
                stroke="rgba(255,255,255,0.18)"
                strokeDasharray="4 4"
                label={{ value: "start", fill: "#64748b", fontSize: 10, position: "insideTopLeft" }}
              />
              <Area
                type="monotone"
                dataKey="equity"
                stroke={stroke}
                strokeWidth={2}
                fill="url(#eq)"
                isAnimationActive={false}
                dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
