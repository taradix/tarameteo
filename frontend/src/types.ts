// Aliases over types generated from backend/openapi.json (`npm run openapi`).
import type { components } from "./api-types";

type Schemas = components["schemas"];

export type SensorEntry = Schemas["SensorEntry"];
export type SensorKind = SensorEntry["kind"];
// Enough to fetch and chart a sensor, even one picked from the URL before the list loads.
export type SensorRef = Pick<SensorEntry, "name" | "kind">;
export type WeatherReading = Schemas["WeatherReading"];
export type AggregateReading = Schemas["AggregateReading"];
export type SensorList = Schemas["SensorList"];

export type WeatherField = "temperature" | "humidity" | "pressure" | "altitude" | "rain" | "snow" | "rssi";
