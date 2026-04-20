import { format, parseISO } from "date-fns";
import type { SensorInfo } from "../types";

interface Props {
  info: SensorInfo;
}

export function SensorStatistics({ info }: Props) {
  const s = info.statistics;
  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <h2 className="mb-3 text-lg font-semibold">Statistics — {info.name}</h2>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm md:grid-cols-4">
        <Stat label="Total readings" value={s.total_readings} />
        <Stat label="Last 24h" value={s.last_24h_readings} />
        <Stat label="Avg temperature" value={fmt(s.average_temperature, "°C")} />
        <Stat label="Avg humidity" value={fmt(s.average_humidity, "%")} />
        <Stat label="Avg pressure" value={fmt(s.average_pressure, "hPa")} />
        <Stat label="Avg RSSI" value={fmt(s.average_rssi, "dBm", 0)} />
        <Stat label="First reading" value={s.first_reading ? format(parseISO(s.first_reading), "PPp") : "—"} />
        <Stat label="Last reading" value={s.last_reading ? format(parseISO(s.last_reading), "PPp") : "—"} />
      </dl>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex flex-col">
      <dt className="text-xs uppercase tracking-wide text-zinc-500">{label}</dt>
      <dd className="font-medium">{value}</dd>
    </div>
  );
}

function fmt(v: number | null, unit: string, digits = 1): string {
  if (v == null) return "—";
  return `${v.toFixed(digits)} ${unit}`;
}
