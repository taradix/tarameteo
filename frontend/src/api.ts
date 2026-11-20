import type { AggregateReading, AlertCreate, ManageRequest, SensorList, WeatherReading } from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "";

export interface SensorFilter {
  names?: string[];
  q?: string;
  limit?: number;
}

type Params = Record<string, string | number | string[] | undefined>;

const weatherPath = (name: string) => `${BASE}/api/sensors/${encodeURIComponent(name)}/weather`;

// Arrays repeat the key (names=a&names=b), as FastAPI expects.
function withQuery(path: string, params: Params): string {
  const query = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined) [v].flat().forEach((x) => query.append(k, String(x)));
  }
  const qs = query.toString();
  return qs ? `${path}?${qs}` : path;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

const post = <T>(path: string, body: unknown) =>
  request<T>(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const api = {
  listSensors: (filter: SensorFilter = {}) => request<SensorList>(withQuery(`${BASE}/api/sensors`, { ...filter })),
  getWeather: (name: string, start: string, end?: string) =>
    request<WeatherReading[]>(withQuery(weatherPath(name), { start, end })),
  getWeatherAggregate: (name: string, start: string, end?: string) =>
    request<AggregateReading[]>(withQuery(`${weatherPath(name)}/aggregate`, { start, end })),
  streamUrl: (name: string) => `${weatherPath(name)}/stream`,
  manageAlerts: (request: ManageRequest) =>
    post<{ status: string }>("/api/alerts/manage", request),
  createAlert: (alert: AlertCreate) =>
    post<{ status: string }>("/api/alerts", alert),
};
