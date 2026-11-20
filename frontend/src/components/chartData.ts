import type { ChartDataset } from "chart.js";
import { addDays, parseISO, startOfDay } from "date-fns";
import { bandColorFor, colorFor } from "../colors";
import { sensorTitle, type AggregateReading, type SensorRef, type WeatherField, type WeatherReading } from "../types";

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

// Each daily aggregate becomes a flat step spanning its day.
function steps(aggData: AggregateReading[], value: (r: AggregateReading) => number | null): Point[] {
  return aggData.flatMap((r) => {
    const v = value(r);
    if (v === null) return [];
    const [start, end] = aggSpan(r);
    return [{ x: start, y: v }, { x: end, y: v }];
  });
}

type Dataset = ChartDataset<"line", Point[]>;

// Points are pre-parsed and drawn as straight lines between them.
function dataset(label: string, data: Point[], color: string, extra: Partial<Dataset> = {}): Dataset {
  return {
    label, data, borderColor: color, backgroundColor: color,
    fill: false, pointRadius: 0, tension: 0, parsing: false, ...extra,
  };
}

function timeseriesDatasets(sensor: SensorRef, field: WeatherField, readings: WeatherReading[], label: string, color: string) {
  const data = readings
    .filter((r) => r.sensor === sensor.name && r[field] != null)
    .map((r) => ({ x: parseISO(r.timestamp).getTime(), y: r[field] as number }))
    .sort((a, b) => a.x - b.x);
  return [dataset(label, data, color)];
}

function aggregateDatasets(
  sensor: SensorRef,
  field: WeatherField,
  aggData: AggregateReading[],
  label: string,
  colorKey: string,
  first: boolean,
): Dataset[] {
  if (BAND_FIELDS.has(field)) {
    const band = bandColorFor(colorKey);
    return [
      // Max boundary — fills down to the immediately following min dataset.
      dataset("", steps(aggData, (r) => bandValues(r, field).max), band, { fill: "+1" }),
      // Min boundary.
      dataset("", steps(aggData, (r) => bandValues(r, field).min), band, { backgroundColor: "transparent" }),
      // Avg line — the one shown in the legend.
      dataset(label, steps(aggData, (r) => bandValues(r, field).avg), colorFor(colorKey), { borderDash: [4, 4] }),
    ];
  }
  // Single aggregate value (rain, snow, …).
  // Use sensor color (not per-field) so precipitation matches other charts;
  // distinguish fields by line style (rain=solid, snow=dashed).
  return [
    dataset(
      first ? sensorTitle(sensor) : "",
      steps(aggData, (r) => singleAggValue(r, field)),
      colorFor(sensor.name),
      field === "snow" ? { borderDash: [4, 4] } : {},
    ),
  ];
}

// fieldLabel names a field in multi-field legends.
export function buildDatasets(
  sensors: SensorRef[],
  fields: WeatherField[],
  readings: WeatherReading[],
  aggregates: AggregateReading[],
  fieldLabel: (field: WeatherField) => string,
): Dataset[] {
  const multiField = fields.length > 1;

  return sensors.flatMap((sensor) => {
    const aggData = sensor.kind === "aggregate"
      ? aggregates
        .filter((r) => r.sensor === sensor.name)
        .sort((a, b) => parseISO(a.timestamp).getTime() - parseISO(b.timestamp).getTime())
      : [];

    return fields.flatMap((field, i) => {
      // When showing multiple fields, differentiate by sensor+field; otherwise by sensor alone.
      const colorKey = multiField ? `${sensor.name}-${field}` : sensor.name;
      const label = multiField ? `${sensorTitle(sensor)} — ${fieldLabel(field)}` : sensorTitle(sensor);
      return sensor.kind === "timeseries"
        ? timeseriesDatasets(sensor, field, readings, label, colorFor(colorKey))
        : aggregateDatasets(sensor, field, aggData, label, colorKey, i === 0);
    });
  });
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
