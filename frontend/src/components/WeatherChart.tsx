import { useMemo } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { format, parseISO } from "date-fns";
import { colorFor } from "../colors";
import type { WeatherField, WeatherReading } from "../types";

interface Props {
  title: string;
  unit: string;
  field: WeatherField;
  sensors: string[];
  readings: WeatherReading[];
}

type Row = { timestamp: string } & Record<string, number | null | string>;

export function WeatherChart({ title, unit, field, sensors, readings }: Props) {
  const data = useMemo(() => pivot(readings, sensors, field), [readings, sensors, field]);

  if (data.length === 0) {
    return (
      <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
        <h2 className="mb-2 text-lg font-semibold">{title}</h2>
        <p className="text-sm text-zinc-500">No data in range.</p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <h2 className="mb-2 text-lg font-semibold">{title}</h2>
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={data} margin={{ top: 8, right: 24, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            dataKey="timestamp"
            tickFormatter={(t) => format(parseISO(t), "MM/dd HH:mm")}
            minTickGap={40}
          />
          <YAxis label={{ value: unit, angle: -90, position: "insideLeft" }} />
          <Tooltip
            labelFormatter={(t) => format(parseISO(t as string), "PPpp")}
            formatter={(v) => [`${v} ${unit}`, ""]}
          />
          <Legend />
          {sensors.map((name) => (
            <Line
              key={name}
              type="monotone"
              dataKey={name}
              name={name}
              stroke={colorFor(name)}
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function pivot(readings: WeatherReading[], sensors: string[], field: WeatherField): Row[] {
  const byTs = new Map<string, Row>();
  for (const r of readings) {
    let row = byTs.get(r.timestamp);
    if (!row) {
      row = { timestamp: r.timestamp };
      byTs.set(r.timestamp, row);
    }
    row[r.sensor] = r[field] ?? null;
  }
  // Ensure every sensor key exists per row so Line components can render.
  for (const row of byTs.values()) {
    for (const s of sensors) if (!(s in row)) row[s] = null;
  }
  return [...byTs.values()].sort(
    (a, b) => parseISO(a.timestamp).getTime() - parseISO(b.timestamp).getTime(),
  );
}
