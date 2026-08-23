"use client";

import { useMemo } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import cureFitJson from "@/data/cure-fit.json";

const AXIS = { fill: "#a1a1aa", fontSize: 10 };
const GRID = "rgba(255,255,255,0.06)";

type Segment = { t_lo_c: number; t_hi_c: number; q10: number };

type CureFit = {
  product: string;
  milestone: string;
  ref_c: number;
  hours_at_ref: number;
  q10_segments: Segment[];
  points: {
    base_c: number;
    base_f: number;
    pds_hours: number;
    model_hours: number;
    pct_error: number;
  }[];
  note: string;
};

const cureFit = cureFitJson as CureFit;

function hoursToService(t: number): number {
  const { ref_c, hours_at_ref, q10_segments } = cureFit;
  const segment =
    q10_segments.find((s) => t >= s.t_lo_c && t <= s.t_hi_c) ??
    (t < ref_c ? q10_segments[0] : q10_segments[q10_segments.length - 1]);
  return hours_at_ref * segment.q10 ** ((ref_c - t) / 10);
}

export function CureFitChart() {
  const curve = useMemo(() => {
    const lo = Math.min(...cureFit.q10_segments.map((s) => s.t_lo_c));
    const hi = Math.max(...cureFit.q10_segments.map((s) => s.t_hi_c));
    const out: { t: number; model: number }[] = [];
    for (let t = lo; t <= hi + 0.01; t += 0.4) {
      out.push({ t: Number(t.toFixed(2)), model: hoursToService(t) });
    }
    return out;
  }, []);

  const pds = cureFit.points.map((p) => ({
    t: p.base_c,
    pds: p.pds_hours,
  }));

  return (
    <div>
      <div className="h-44 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={curve}
            margin={{ top: 8, right: 8, left: -8, bottom: 0 }}
          >
            <CartesianGrid stroke={GRID} vertical={false} />
            <XAxis
              dataKey="t"
              type="number"
              domain={["dataMin", "dataMax"]}
              unit="°C"
              tick={AXIS}
              axisLine={{ stroke: GRID }}
              tickLine={false}
            />
            <YAxis
              unit=" h"
              tick={AXIS}
              axisLine={false}
              tickLine={false}
              width={48}
            />
            <Tooltip
              contentStyle={{
                background: "oklch(0.205 0 0)",
                border: "1px solid oklch(1 0 0 / 10%)",
                borderRadius: 8,
                fontSize: 11,
              }}
              formatter={(value, name) => {
                const n = typeof value === "number" ? value.toFixed(1) : "—";
                return [`${n} h`, String(name)];
              }}
              labelFormatter={(label) => `${label} °C`}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Line
              type="monotone"
              dataKey="model"
              name="Q10 model"
              stroke="#6ee7b7"
              strokeWidth={1.8}
              dot={false}
              isAnimationActive={false}
            />
            <Scatter
              data={pds}
              dataKey="pds"
              name="PDS table"
              fill="#fcd34d"
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <table className="mt-2 w-full text-left text-[11px]">
        <thead className="text-[10px] tracking-wider text-muted-foreground uppercase">
          <tr>
            <th className="py-0.5 font-medium">T</th>
            <th className="py-0.5 font-medium">PDS</th>
            <th className="py-0.5 font-medium">Q10</th>
            <th className="py-0.5 font-medium">err</th>
          </tr>
        </thead>
        <tbody className="font-mono text-muted-foreground">
          {cureFit.points.map((p) => (
            <tr key={p.base_c}>
              <td className="py-0.5">{p.base_c.toFixed(1)} °C</td>
              <td className="py-0.5">{p.pds_hours.toFixed(0)} h</td>
              <td className="py-0.5">{p.model_hours.toFixed(1)} h</td>
              <td className="py-0.5">{p.pct_error.toFixed(1)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-[11px] leading-snug text-muted-foreground">
        {cureFit.product} · {cureFit.note}
      </p>
    </div>
  );
}
