import type { components } from "./api-types";

type Schemas = components["schemas"];

export type SensorEntry = Schemas["SensorEntry"];
export type WeatherReading = Schemas["WeatherReading"];
export type AggregateReading = Schemas["AggregateReading"];

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

// Sorts nearest first, within radius km when given.
export type Near = { latitude: number; longitude: number; radius?: number };

const near = ({ latitude, longitude, radius }: Near) =>
  `?latitude=${latitude}&longitude=${longitude}${radius ? `&radius=${radius}` : ""}`;

export const api = {
  // GET /api/sensors returns dict[str, list[SensorEntry]], which has no named schema.
  listSensors: (around?: Near) => get<{ sensors: SensorEntry[] }>(`/api/sensors${around ? near(around) : ""}`),
  getWeather: (name: string, start: string) => get<WeatherReading[]>(weather(name, "", start)),
  getWeatherAggregate: (name: string, start: string) =>
    get<AggregateReading[]>(weather(name, "/aggregate", start)),
};
