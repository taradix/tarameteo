import { useCallback, useLayoutEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import {
  Chart as ChartJS,
  TimeScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
  Decimation,
  type ChartOptions,
  type ChartData,
} from "chart.js";
import { Line } from "react-chartjs-2";
import "chartjs-adapter-date-fns";
import zoomPlugin from "chartjs-plugin-zoom";
import { parseISO } from "date-fns";
import { colorFor } from "../colors";
import type { WeatherField, WeatherReading } from "../types";

ChartJS.register(TimeScale, LinearScale, PointElement, LineElement, Tooltip, Legend, Decimation, zoomPlugin);

interface Props {
  title: string;
  unit: string;
  field: WeatherField;
  sensors: string[];
  readings: WeatherReading[];
  start: Date;
  end: Date | null;
  onRangeExtend?: (start: Date, end: Date | null) => void;
}

type Point = { x: number; y: number };

export function WeatherChart({ title, unit, field, sensors, readings, start, end, onRangeExtend }: Props) {
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
    // Don't extend end in live mode (end === null); the stream covers "now".
    const newEnd = endRef.current !== null && max > dataMax ? new Date(max) : endRef.current;

    if (newStart !== startRef.current || newEnd !== endRef.current) {
      onRangeExtendRef.current?.(newStart, newEnd);
    }
  }, []);

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
        parsing: false,
      })),
    }),
    [readings, sensors, field],
  );

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
        legend: { position: "bottom" },
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

  const hasData = readings.length > 0;

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
