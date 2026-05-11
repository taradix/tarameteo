import type { AggregateReading, SensorsList, WeatherReading } from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "";

async function get<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(`${BASE}${path}`, window.location.origin);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined) url.searchParams.set(k, String(v));
    }
  }
  const res = await fetch(url.toString().replace(window.location.origin, ""));
  if (!res.ok) {
    throw new ApiError(res.status, `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

export const api = {
  listSensors: () => get<SensorsList>("/api/sensors"),
  getWeather: (name: string, start: string, end?: string, limit?: number) =>
    get<WeatherReading[]>(
      `/api/sensors/${encodeURIComponent(name)}/weather`,
      { start, end, limit },
    ),
  getWeatherAggregate: (name: string, start: string, end?: string, limit?: number) =>
    get<AggregateReading[]>(
      `/api/sensors/${encodeURIComponent(name)}/weather/aggregate`,
      { start, end, limit },
    ),
};
