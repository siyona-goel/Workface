"use client";

import { useMemo } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatTick, type RibbonEval } from "@/lib/ribbon-data";

const AXIS = { fill: "#a1a1aa", fontSize: 10 };
const GRID = "rgba(255,255,255,0.06)";

type Point = {
  ts: string;
  t_air: number | null;
  t_surf: number | null;
  t_dew: number | null;
  dew_stack: number | null;
  offset_delta: number | null;
};

type Props = {
  evaluation: RibbonEval;
};

function ThermalTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: { payload: Point }[];
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  const bandTop =
    row.t_dew != null && row.offset_delta != null
      ? row.t_dew + row.offset_delta
      : null;

  return (
    <div className="rounded-md border border-border bg-background px-2.5 py-2 text-[11px] shadow-lg">
      <p className="mb-1 font-mono text-muted-foreground">{formatTick(row.ts)}</p>
      <p>T_air {fmt(row.t_air)}</p>
      <p>T_surf {fmt(row.t_surf)}</p>
      <p>T_dew {fmt(row.t_dew)}</p>
      {bandTop != null ? <p>Offset floor {fmt(bandTop)}</p> : null}
    </div>
  );
}

function fmt(n: number | null) {
  return n == null ? "—" : `${n.toFixed(1)} °C`;
}

export function ThermalChart({ evaluation }: Props) {
  const delta = evaluation.offset_delta_c;
  const showBand = delta != null && delta > 0;

  const data = useMemo<Point[]>(
    () =>
      evaluation.hours.map((h) => ({
        ts: h.ts,
        t_air: h.t_air_c ?? null,
        t_surf: h.t_surf_c ?? null,
        t_dew: h.t_dew_c ?? null,
        dew_stack: h.t_dew_c ?? null,
        offset_delta: h.t_dew_c != null && showBand ? delta : null,
      })),
    [delta, evaluation.hours, showBand],
  );

  const hasSeries = data.some(
    (d) => d.t_air != null || d.t_surf != null || d.t_dew != null,
  );

  if (!hasSeries) {
    return (
      <p className="py-8 text-center text-xs text-muted-foreground">
        No T_air / T_surf / T_dew series on this evaluation.
      </p>
    );
  }

  return (
    <div className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart
          data={data}
          margin={{ top: 8, right: 8, left: -12, bottom: 0 }}
        >
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis
            dataKey="ts"
            minTickGap={28}
            tickFormatter={(ts) => formatTick(String(ts))}
            tick={AXIS}
            axisLine={{ stroke: GRID }}
            tickLine={false}
          />
          <YAxis
            unit="°C"
            tick={AXIS}
            axisLine={false}
            tickLine={false}
            width={48}
          />
          <Tooltip content={<ThermalTooltip />} />
          <Legend
            wrapperStyle={{ fontSize: 11, color: "#a1a1aa" }}
            iconType="plainline"
          />
          {showBand ? (
            <>
              <Area
                stackId="offset"
                dataKey="dew_stack"
                name="T_dew (stack)"
                fill="transparent"
                stroke="none"
                legendType="none"
                activeDot={false}
                isAnimationActive={false}
              />
              <Area
                stackId="offset"
                dataKey="offset_delta"
                name={`Offset +${delta} °C`}
                fill="#fcd34d55"
                stroke="#fcd34d99"
                strokeWidth={1}
                activeDot={false}
                isAnimationActive={false}
              />
            </>
          ) : null}
          <Line
            type="monotone"
            dataKey="t_dew"
            name="T_dew"
            stroke="#7dd3fc"
            strokeWidth={1.6}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="t_surf"
            name="T_surf"
            stroke="#f9a8d4"
            strokeWidth={1.8}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="t_air"
            name="T_air"
            stroke="#e2e8f0"
            strokeWidth={1.4}
            strokeDasharray="4 3"
            dot={false}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
