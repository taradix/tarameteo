import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { buildDatasets, extendedRange } from "./chartData";
import type { AggregateReading, WeatherReading } from "../types";

// Local-time timestamps, since daily aggregates span local days.
const at = (day: number, hour = 0) => new Date(2026, 0, day, hour).getTime();
const iso = (day: number, hour = 0) => new Date(at(day, hour)).toISOString();

function reading(sensor: string, day: number, hour: number, temperature: number, rain?: number): WeatherReading {
  return {
    sensor, timestamp: iso(day, hour), temperature, humidity: 50, pressure: 1000,
    latitude: 0, longitude: 0, rain,
  };
}

const ts = { name: "ts", kind: "timeseries" } as const;
const agg = { name: "agg", kind: "aggregate" } as const;

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(at(10, 12));
});

afterEach(() => {
  vi.useRealTimers();
});

describe("buildDatasets", () => {
  it("sorts a sensor's readings and ignores other sensors and missing values", () => {
    const readings = [
      reading("ts", 9, 2, 20, 1),
      reading("ts", 9, 1, 10),
      reading("other", 9, 1, 99, 9),
    ];
    const [temp, rain] = buildDatasets([ts], ["temperature", "rain"], readings, []);
    expect(temp.label).toBe("ts — Temperature");
    expect(temp.data).toEqual([{ x: at(9, 1), y: 10 }, { x: at(9, 2), y: 20 }]);
    expect(rain.label).toBe("ts — Rain");
    expect(rain.data).toEqual([{ x: at(9, 2), y: 1 }]);
  });

  it("labels by sensor alone for a single field", () => {
    const [ds] = buildDatasets([ts], ["temperature"], [reading("ts", 9, 1, 10)], []);
    expect(ds.label).toBe("ts");
  });

  it("draws band aggregates as max, min, then avg steps over each day", () => {
    const aggregates: AggregateReading[] = [
      { sensor: "agg", timestamp: iso(8, 23), temperature_min: 1, temperature_avg: 2, temperature_max: 3 },
    ];
    const [max, min, avg] = buildDatasets([agg], ["temperature"], [], aggregates);
    const day = (y: number) => [{ x: at(8), y }, { x: at(9), y }];
    expect(max).toMatchObject({ label: "", fill: "+1", data: day(3) });
    expect(min).toMatchObject({ label: "", fill: false, data: day(1) });
    expect(avg).toMatchObject({ label: "agg", data: day(2) });
  });

  it("stops today's step at the observation instead of midnight", () => {
    const aggregates: AggregateReading[] = [{ sensor: "agg", timestamp: iso(10, 6), rain: 4 }];
    const [rain] = buildDatasets([agg], ["rain"], [], aggregates);
    expect(rain.data).toEqual([{ x: at(10), y: 4 }, { x: at(10, 6), y: 4 }]);
  });

  it("sorts aggregates and skips missing values", () => {
    const aggregates: AggregateReading[] = [
      { sensor: "agg", timestamp: iso(8, 12), rain: 2 },
      { sensor: "agg", timestamp: iso(7, 12), rain: 1 },
      { sensor: "agg", timestamp: iso(6, 12) },
      { sensor: "other", timestamp: iso(6, 12), rain: 9 },
    ];
    const [rain] = buildDatasets([agg], ["rain"], [], aggregates);
    expect(rain.data.map((p) => p.y)).toEqual([1, 1, 2, 2]);
  });

  it("labels only the first precipitation field and dashes snow", () => {
    const aggregates: AggregateReading[] = [{ sensor: "agg", timestamp: iso(8, 12), rain: 1, snow: 2 }];
    const [rain, snow] = buildDatasets([agg], ["rain", "snow"], [], aggregates);
    expect(rain.label).toBe("agg");
    expect(rain.borderDash).toBeUndefined();
    expect(snow.label).toBe("");
    expect(snow.borderDash).toEqual([4, 4]);
  });
});

describe("extendedRange", () => {
  const start = new Date(at(5));
  const end = new Date(at(9));

  it("returns null while inside the loaded range", () => {
    expect(extendedRange(at(6), at(8), start, end)).toBeNull();
  });

  it("extends backward and forward", () => {
    expect(extendedRange(at(4), at(8), start, end)).toEqual([new Date(at(4)), end]);
    expect(extendedRange(at(6), at(10), start, end)).toEqual([start, new Date(at(10))]);
  });

  it("never extends forward in live mode", () => {
    expect(extendedRange(at(6), at(20), start, null)).toBeNull();
    expect(extendedRange(at(4), at(20), start, null)).toEqual([new Date(at(4)), null]);
  });
});
