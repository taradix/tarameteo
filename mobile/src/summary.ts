import type { WeatherReading } from "@/api";

export type Trend = "rising" | "falling" | undefined;

const TREND_WINDOW_MS = 3 * 3600_000;
// Changes smaller than this over TREND_WINDOW_MS count as steady; tune to taste.
const TEMPERATURE_STEP = 0.5;
const PRESSURE_STEP = 1;

export interface Summary {
  latest: WeatherReading;
  min: number;
  max: number;
  temperatureTrend: Trend;
  pressureTrend: Trend;
}

function trend(now: number, then: number | undefined, step: number): Trend {
  if (then === undefined || Math.abs(now - then) < step) return undefined;
  return now > then ? "rising" : "falling";
}

// Readings come sorted oldest first, as the API returns them.
export function summarize(readings: WeatherReading[]): Summary | undefined {
  const latest = readings.at(-1);
  if (!latest) return undefined;
  const cutoff = Date.parse(latest.timestamp) - TREND_WINDOW_MS;
  const before = readings.findLast((r) => Date.parse(r.timestamp) <= cutoff);
  const temperatures = readings.map((r) => r.temperature);
  return {
    latest,
    min: Math.min(...temperatures),
    max: Math.max(...temperatures),
    temperatureTrend: trend(latest.temperature, before?.temperature, TEMPERATURE_STEP),
    pressureTrend: trend(latest.pressure, before?.pressure, PRESSURE_STEP),
  };
}

export type Age = { unit: "minutes" | "hours" | "days"; count: number };

export function age(timestamp: string, now: number): Age {
  const minutes = Math.max(0, Math.floor((now - Date.parse(timestamp)) / 60_000));
  if (minutes < 60) return { unit: "minutes", count: minutes };
  if (minutes < 24 * 60) return { unit: "hours", count: Math.floor(minutes / 60) };
  return { unit: "days", count: Math.floor(minutes / (24 * 60)) };
}
