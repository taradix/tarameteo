// Hand-written mirror of the backend's Pydantic response models.
// Replace with `npm run generate:types` output once the backend's
// openapi.json is kept up to date.

export interface WeatherReading {
  sensor: string;
  timestamp: string;
  temperature: number;
  humidity: number;
  pressure: number;
  altitude: number | null;
  rssi: number | null;
  retry_count: number | null;
}

export interface SensorStatistics {
  total_readings: number;
  first_reading: string | null;
  last_reading: string | null;
  last_24h_readings: number;
  average_temperature: number | null;
  average_humidity: number | null;
  average_pressure: number | null;
  average_rssi: number | null;
}

export interface SensorInfo {
  name: string;
  statistics: SensorStatistics;
}

export interface SensorsList {
  sensors: string[];
}

export type WeatherField = "temperature" | "humidity" | "pressure" | "altitude" | "rssi";
