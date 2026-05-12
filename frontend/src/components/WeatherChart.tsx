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
import { addDays, parseISO, startOfDay } from "date-fns";
import { bandColorFor, colorFor } from "../colors";
import type { AggregateReading, SensorEntry, WeatherField, WeatherReading } from "../types";

ChartJS.register(
  TimeScale, LinearScale, PointElement, LineElement, Filler,
  Tooltip, Legend, Decimation, zoomPlugin,
);

// These fields have min/avg/max structure in AggregateReading; all others are single values.
const BAND_FIELDS = new Set<WeatherField>(["temperature", "humidity", "pressure"]);

interface Props {
  title: string;
  unit: string;
  fields: WeatherField[];
  sensors: SensorEntry[];
  readings: WeatherReading[];
  aggregates: AggregateReading[];
  start: Date;
  end: Date | null;
  onRangeExtend?: (start: Date, end: Date | null) => void;
}

type Point = { x: number; y: number };

function aggSpan(r: AggregateReading): [number, number] {
  const dayStart = startOfDay(parseISO(r.timestamp));
  return [dayStart.getTime(), addDays(dayStart, 1).getTime()];
}

function bandValues(
  r: AggregateReading,
  field: WeatherField,
): { min: number | null; avg: number | null; max: number | null } {
  const key = field as "temperature" | "humidity" | "pressure";
  return { min: r[`${key}_min`] ?? null, avg: r[`${key}_avg`] ?? null, max: r[`${key}_max`] ?? null };
}

function singleAggValue(r: AggregateReading, field: WeatherField): number | null {
  const map: Partial<Record<WeatherField, number | null>> = { rain: r.rain, snow: r.snow };
  return map[field] ?? null;
}

// Capitalise the field name for use in multi-field dataset labels.
function fieldLabel(field: WeatherField): string {
  return field.charAt(0).toUpperCase() + field.slice(1);
}

export function WeatherChart({ title, unit, fields, sensors, readings, aggregates, start, end, onRangeExtend }: Props) {
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
    const multiField = fields.length > 1;

    for (const sensor of sensors) {
      for (const field of fields) {
        // When showing multiple fields, differentiate by sensor+field; otherwise by sensor alone.
        const colorKey = multiField ? `${sensor.name}-${field}` : sensor.name;
        const color = colorFor(colorKey);
        const label = multiField ? `${sensor.name} — ${fieldLabel(field)}` : sensor.name;

        if (sensor.kind === "timeseries") {
          datasets.push({
            label,
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

          if (BAND_FIELDS.has(field)) {
            // Max boundary — fills down to the immediately following min dataset.
            datasets.push({
              label: "",
              data: aggData.flatMap((r) => {
                const v = bandValues(r, field).max;
                if (v === null) return [];
                const [start, end] = aggSpan(r);
                return [{ x: start, y: v }, { x: end, y: v }];
              }),
              borderColor: bandColorFor(colorKey),
              backgroundColor: bandColorFor(colorKey),
              fill: "+1",
              pointRadius: 0,
              tension: 0,
              parsing: false,
            });
            // Min boundary.
            datasets.push({
              label: "",
              data: aggData.flatMap((r) => {
                const v = bandValues(r, field).min;
                if (v === null) return [];
                const [start, end] = aggSpan(r);
                return [{ x: start, y: v }, { x: end, y: v }];
              }),
              borderColor: bandColorFor(colorKey),
              backgroundColor: "transparent",
              fill: false,
              pointRadius: 0,
              tension: 0,
              parsing: false,
            });
            // Avg line — the one shown in the legend.
            datasets.push({
              label,
              data: aggData.flatMap((r) => {
                const v = bandValues(r, field).avg;
                if (v === null) return [];
                const [start, end] = aggSpan(r);
                return [{ x: start, y: v }, { x: end, y: v }];
              }),
              borderColor: color,
              backgroundColor: color,
              borderDash: [4, 4],
              fill: false,
              pointRadius: 0,
              tension: 0,
              parsing: false,
            });
          } else {
            // Single aggregate value (rain, snow, …).
            datasets.push({
              label,
              data: aggData.flatMap((r) => {
                const v = singleAggValue(r, field);
                if (v === null) return [];
                const [start, end] = aggSpan(r);
                return [{ x: start, y: v }, { x: end, y: v }];
              }),
              borderColor: color,
              backgroundColor: color,
              fill: false,
              pointRadius: 0,
              tension: 0,
              parsing: false,
            });
          }
        }
      }
    }

    return { datasets };
  }, [readings, aggregates, sensors, fields]);

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
            // Hide the unlabelled band-boundary datasets.
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
