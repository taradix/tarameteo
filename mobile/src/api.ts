import type { components } from "./api-types";

type Schemas = components["schemas"];

export type SensorEntry = Schemas["SensorEntry"];
export type WeatherReading = Schemas["WeatherReading"];
export type AggregateReading = Schemas["AggregateReading"];
export type Cluster = Schemas["Cluster"];

// Inlined at build time; override in .env.local to point at a dev backend.
const BASE = process.env.EXPO_PUBLIC_API_BASE ?? "https://meteo.taram.ca";

export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    throw new ApiError(res.status, `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

const weather = (name: string, suffix: string, start: string) =>
  `/api/sensors/${encodeURIComponent(name)}/weather${suffix}?start=${encodeURIComponent(start)}`;

// Clients ignore sensor kinds they don't know (see CONTRIBUTING.rst).
export const KINDS: readonly string[] = ["timeseries", "aggregate"];

// Filters for GET /api/sensors; latitude/longitude sort nearest first, within radius km when given.
// bbox is "west,south,east,north" in degrees.
export type SensorFilter = {
  names?: string[];
  q?: string;
  bbox?: string;
  latitude?: number;
  longitude?: number;
  radius?: number;
  limit?: number;
};

// Arrays repeat the key (names=a&names=b), as FastAPI expects; undefined values are left out.
const query = (filter: Record<string, string | number | string[] | undefined>) => {
  const pairs = Object.entries(filter).flatMap(([key, value]) =>
    value === undefined ? [] : [value].flat().map((v) => `${key}=${encodeURIComponent(v)}`),
  );
  return pairs.length ? `?${pairs.join("&")}` : "";
};

export const api = {
  listSensors: (filter: SensorFilter = {}) => get<Schemas["SensorList"]>(`/api/sensors${query(filter)}`),
  listClusters: (bbox: string, zoom: number) =>
    get<Schemas["ClusterList"]>(`/api/sensors/clusters${query({ bbox, zoom })}`),
  getWeather: (name: string, start: string) => get<WeatherReading[]>(weather(name, "", start)),
  getWeatherAggregate: (name: string, start: string) =>
    get<AggregateReading[]>(weather(name, "/aggregate", start)),
};
