import { useMemo } from "react";
import {
  Chart as ChartJS,
  TimeScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
  type ChartOptions,
  type ChartData,
} from "chart.js";
import { Line } from "react-chartjs-2";
import "chartjs-adapter-date-fns";
import zoomPlugin from "chartjs-plugin-zoom";
import { parseISO } from "date-fns";
import { colorFor } from "../colors";
import type { WeatherField, WeatherReading } from "../types";

ChartJS.register(TimeScale, LinearScale, PointElement, LineElement, Tooltip, Legend, zoomPlugin);

interface Props {
  title: string;
  unit: string;
  field: WeatherField;
  sensors: string[];
  readings: WeatherReading[];
}

type Point = { x: number; y: number };

export function WeatherChart({ title, unit, field, sensors, readings }: Props) {
  const data = useMemo<ChartData<"line", Point[]>>(
    () => ({
      datasets: sensors.map((name) => ({
        label: name,
        data: readings
          .filter((r) => r.sensor === name && r[field] != null)
          .map((r) => ({ x: parseISO(r.timestamp).getTime(), y: r[field] as number }))
          .sort((a, b) => a.x - b.x),
        borderColor: colorFor(name),
        backgroundColor: colorFor(name),
        pointRadius: 0,
        tension: 0,
      })),
    }),
    [readings, sensors, field],
  );

  const options = useMemo<ChartOptions<"line">>(
    () => ({
      responsive: true,
      animation: { duration: 400 },
      scales: {
        x: {
          type: "time",
          time: {
            displayFormats: {
              minute: "MM/dd HH:mm",
              hour: "MM/dd HH:mm",
              day: "MM/dd",
            },
          },
          ticks: { maxTicksLimit: 8 },
        },
        y: {
          title: { display: true, text: unit },
        },
      },
      plugins: {
        legend: { position: "bottom" },
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y} ${unit}`,
          },
        },
        zoom: {
          pan: { enabled: true, mode: "x" },
          zoom: {
            pinch: { enabled: true },
            wheel: { enabled: false },
            mode: "x",
          },
        },
      },
    }),
    [unit],
  );

  const hasData = readings.length > 0;

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <h2 className="mb-2 text-lg font-semibold">{title}</h2>
      {hasData ? (
        <Line data={data} options={options} />
      ) : (
        <p className="text-sm text-zinc-500">No data in range.</p>
      )}
    </div>
  );
}
