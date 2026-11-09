import type { ChartDataset } from "chart.js";
import { addDays, parseISO, startOfDay } from "date-fns";
import { bandColorFor, colorFor } from "../colors";
import type { AggregateReading, SensorEntry, WeatherField, WeatherReading } from "../types";

// These fields have min/avg/max structure in AggregateReading; all others are single values.
const BAND_FIELDS = new Set<WeatherField>(["temperature", "humidity", "pressure"]);

export type Point = { x: number; y: number };

function aggSpan(r: AggregateReading): [number, number] {
  const ts = parseISO(r.timestamp);
  const dayStart = startOfDay(ts);
  const dayEnd = addDays(dayStart, 1);
  // For a day still in progress, stop at the observation timestamp rather than
  // extending to midnight — that would imply a prediction, not recorded data.
  const end = dayEnd.getTime() > Date.now() ? ts.getTime() : dayEnd.getTime();
  return [dayStart.getTime(), end];
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

// Each daily aggregate becomes a flat step spanning its day.
function steps(aggData: AggregateReading[], value: (r: AggregateReading) => number | null): Point[] {
  return aggData.flatMap((r) => {
    const v = value(r);
    if (v === null) return [];
    const [start, end] = aggSpan(r);
    return [{ x: start, y: v }, { x: end, y: v }];
  });
}

export function buildDatasets(
  sensors: SensorEntry[],
  fields: WeatherField[],
  readings: WeatherReading[],
  aggregates: AggregateReading[],
): ChartDataset<"line", Point[]>[] {
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
            data: steps(aggData, (r) => bandValues(r, field).max),
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
            data: steps(aggData, (r) => bandValues(r, field).min),
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
            data: steps(aggData, (r) => bandValues(r, field).avg),
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
          // Use sensor color (not per-field) so precipitation matches other charts;
          // distinguish fields by line style (rain=solid, snow=dashed).
          const aggColor = colorFor(sensor.name);
          const aggLabel = fields.indexOf(field) === 0 ? sensor.name : "";
          datasets.push({
            label: aggLabel,
            data: steps(aggData, (r) => singleAggValue(r, field)),
            borderColor: aggColor,
            backgroundColor: aggColor,
            ...(field === "snow" ? { borderDash: [4, 4] } : {}),
            fill: false,
            pointRadius: 0,
            tension: 0,
            parsing: false,
          });
        }
      }
    }
  }

  return datasets;
}

// After a pan/zoom past the loaded data, return the widened range, or null if
// still inside it. Live mode (end=null) never extends forward.
export function extendedRange(
  min: number,
  max: number,
  start: Date,
  end: Date | null,
): [Date, Date | null] | null {
  const newStart = min < start.getTime() ? new Date(min) : start;
  const newEnd = end !== null && max > end.getTime() ? new Date(max) : end;
  return newStart !== start || newEnd !== end ? [newStart, newEnd] : null;
}
