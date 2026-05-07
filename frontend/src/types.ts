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

export interface SensorsList {
  sensors: string[];
}

export type WeatherField = "temperature" | "humidity" | "pressure" | "altitude" | "rssi";
