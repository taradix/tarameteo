import { useCallback, useLayoutEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import {
  Chart as ChartJS,
  TimeScale,
  LinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
  Decimation,
  type ChartOptions,
  type ChartData,
  type ChartDataset,
} from "chart.js";
import { Line } from "react-chartjs-2";
import "chartjs-adapter-date-fns";
import zoomPlugin from "chartjs-plugin-zoom";
import { parseISO } from "date-fns";
import { bandColorFor, colorFor } from "../colors";
import type { AggregateReading, SensorEntry, WeatherField, WeatherReading } from "../types";

ChartJS.register(
  TimeScale, LinearScale, PointElement, LineElement, Filler,
  Tooltip, Legend, Decimation, zoomPlugin,
);

interface Props {
  title: string;
  unit: string;
  field: WeatherField;
  sensors: SensorEntry[];
  readings: WeatherReading[];
  aggregates: AggregateReading[];
  start: Date;
  end: Date | null;
  onRangeExtend?: (start: Date, end: Date | null) => void;
}

type Point = { x: number; y: number };

function aggValues(
  r: AggregateReading,
  field: WeatherField,
): { min: number | null; avg: number | null; max: number | null } {
  const key = field as "temperature" | "humidity" | "pressure";
  return {
    min: r[`${key}_min`] ?? null,
    avg: r[`${key}_avg`] ?? null,
    max: r[`${key}_max`] ?? null,
  };
}

export function WeatherChart({ title, unit, field, sensors, readings, aggregates, start, end, onRangeExtend }: Props) {
  const { t } = useTranslation();
  const chartRef = useRef<ChartJS<"line">>(null);

  const startRef = useRef(start);
  const endRef = useRef(end);
  const onRangeExtendRef = useRef(onRangeExtend);
  useLayoutEffect(() => {
    startRef.current = start;
    endRef.current = end;
    onRangeExtendRef.current = onRangeExtend;
  });

  const handleZoomPanComplete = useCallback(({ chart }: { chart: ChartJS }) => {
    const { min, max } = chart.scales.x;
    const dataMin = startRef.current.getTime();
    const dataMax = endRef.current?.getTime() ?? Date.now();

    const newStart = min < dataMin ? new Date(min) : startRef.current;
    const newEnd = endRef.current !== null && max > dataMax ? new Date(max) : endRef.current;

    if (newStart !== startRef.current || newEnd !== endRef.current) {
      onRangeExtendRef.current?.(newStart, newEnd);
    }
  }, []);

  const data = useMemo<ChartData<"line", Point[]>>(() => {
    const datasets: ChartDataset<"line", Point[]>[] = [];

    for (const sensor of sensors) {
      const color = colorFor(sensor.name);

      if (sensor.kind === "timeseries") {
        datasets.push({
          label: sensor.name,
          data: readings
            .filter((r) => r.sensor === sensor.name && r[field] != null)
            .map((r) => ({ x: parseISO(r.timestamp).getTime(), y: r[field] as number }))
            .sort((a, b) => a.x - b.x),
          borderColor: color,
          backgroundColor: color,
          pointRadius: 0,
          tension: 0,
          parsing: false,
        });
      } else {
        const aggData = aggregates
          .filter((r) => r.sensor === sensor.name)
          .sort((a, b) => parseISO(a.timestamp).getTime() - parseISO(b.timestamp).getTime());

        // Max line — fills down to the immediately following min dataset.
        datasets.push({
          label: "",
          data: aggData
            .map((r) => ({ x: parseISO(r.timestamp).getTime(), y: aggValues(r, field).max }))
            .filter((p): p is Point => p.y !== null),
          borderColor: bandColorFor(sensor.name),
          backgroundColor: bandColorFor(sensor.name),
          fill: "+1",
          pointRadius: 0,
          tension: 0,
          parsing: false,
        });

        // Min line — bottom boundary of the band.
        datasets.push({
          label: "",
          data: aggData
            .map((r) => ({ x: parseISO(r.timestamp).getTime(), y: aggValues(r, field).min }))
            .filter((p): p is Point => p.y !== null),
          borderColor: bandColorFor(sensor.name),
          backgroundColor: "transparent",
          fill: false,
          pointRadius: 0,
          tension: 0,
          parsing: false,
        });

        // Avg line — shown in legend as the sensor label.
        datasets.push({
          label: sensor.name,
          data: aggData
            .map((r) => ({ x: parseISO(r.timestamp).getTime(), y: aggValues(r, field).avg }))
            .filter((p): p is Point => p.y !== null),
          borderColor: color,
          backgroundColor: color,
          borderDash: [4, 4],
          fill: false,
          pointRadius: 3,
          tension: 0,
          parsing: false,
        });
      }
    }

    return { datasets };
  }, [readings, aggregates, sensors, field]);

  const options = useMemo<ChartOptions<"line">>(
    () => ({
      responsive: true,
      animation: false,
      scales: {
        x: {
          type: "time",
          min: start.getTime(),
          ...(end ? { max: end.getTime() } : {}),
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
        legend: {
          position: "bottom",
          labels: {
            filter: (item) => item.text !== "",
          },
        },
        decimation: {
          enabled: true,
          algorithm: "lttb",
          samples: 500,
        },
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y} ${unit}`,
          },
        },
        zoom: {
          pan: { enabled: true, mode: "x", onPanComplete: handleZoomPanComplete },
          zoom: {
            pinch: { enabled: true },
            wheel: { enabled: false },
            mode: "x",
            onZoomComplete: handleZoomPanComplete,
          },
        },
      },
    }),
    [unit, start, end, handleZoomPanComplete],
  );

  const hasData = readings.length > 0 || aggregates.length > 0;

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <h2 className="mb-2 text-lg font-semibold">{title}</h2>
      {hasData ? (
        <Line ref={chartRef} data={data} options={options} />
      ) : (
        <p className="text-sm text-zinc-500">{t("chart.noData")}</p>
      )}
    </div>
  );
}
