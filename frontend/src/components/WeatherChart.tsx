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
} from "chart.js";
import { Line } from "react-chartjs-2";
import "chartjs-adapter-date-fns";
import zoomPlugin from "chartjs-plugin-zoom";
import type { AggregateReading, SensorEntry, WeatherField, WeatherReading } from "../types";
import { buildDatasets, extendedRange, type Point } from "./chartData";

ChartJS.register(
  TimeScale, LinearScale, PointElement, LineElement, Filler,
  Tooltip, Legend, Decimation, zoomPlugin,
);

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
    const range = extendedRange(min, max, startRef.current, endRef.current);
    if (range) {
      onRangeExtendRef.current?.(...range);
    }
  }, []);

  const data = useMemo<ChartData<"line", Point[]>>(
    () => ({ datasets: buildDatasets(sensors, fields, readings, aggregates) }),
    [readings, aggregates, sensors, fields],
  );

  const options = useMemo<ChartOptions<"line">>(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
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
        <div className="h-64">
          <Line ref={chartRef} data={data} options={options} />
        </div>
      ) : (
        <p className="text-sm text-zinc-500">{t("chart.noData")}</p>
      )}
    </div>
  );
}
