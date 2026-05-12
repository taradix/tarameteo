// Hand-written mirror of the backend's Pydantic response models.

export type SensorKind = "timeseries" | "aggregate";

export interface SensorEntry {
  name: string;
  kind: SensorKind;
}

export interface SensorsList {
  sensors: SensorEntry[];
}

export interface WeatherReading {
  sensor: string;
  timestamp: string;
  temperature: number;
  humidity: number;
  pressure: number;
  altitude: number | null;
  rain: number | null;
  snow: number | null;
  rssi: number | null;
  retry_count: number | null;
}

export interface AggregateReading {
  sensor: string;
  timestamp: string;
  temperature_min: number | null;
  temperature_avg: number | null;
  temperature_max: number | null;
  humidity_min: number | null;
  humidity_avg: number | null;
  humidity_max: number | null;
  pressure_min: number | null;
  pressure_avg: number | null;
  pressure_max: number | null;
  rain: number | null;
  snow: number | null;
}

export type WeatherField = "temperature" | "humidity" | "pressure" | "altitude" | "rain" | "snow" | "rssi";
