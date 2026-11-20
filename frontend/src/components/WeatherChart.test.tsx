import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { WeatherChart } from "./WeatherChart";
import type { AggregateReading, WeatherReading } from "../types";

const at = (day: number, hour = 0) => new Date(2026, 0, day, hour);
const iso = (day: number, hour = 0) => at(day, hour).toISOString();

function reading(sensor: string, day: number, hour: number, temperature: number): WeatherReading {
  return {
    sensor,
    timestamp: iso(day, hour),
    temperature,
    humidity: 50,
    pressure: 1000,
    latitude: 45.5,
    longitude: -73.6,
  };
}

function aggregate(sensor: string, day: number, temp_min: number, temp_avg: number, temp_max: number): AggregateReading {
  return {
    sensor,
    timestamp: iso(day, 12),
    temperature_min: temp_min,
    temperature_avg: temp_avg,
    temperature_max: temp_max,
  };
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(at(10, 12));
});

afterEach(() => {
  vi.useRealTimers();
});

describe("WeatherChart", () => {
  describe("empty state", () => {
    it("shows 'no data' message when there are no readings", () => {
      render(
        <WeatherChart
          title="Temperature"
          unit="°C"
          fields={["temperature"]}
          sensors={[{ name: "outdoor", kind: "timeseries" }]}
          readings={[]}
          aggregates={[]}
          start={at(5)}
          end={at(10)}
        />,
      );
      expect(screen.getByText(/no data in range/i)).toBeInTheDocument();
    });

    it("says it's loading rather than empty while readings load", () => {
      render(
        <WeatherChart
          title="Temperature"
          unit="°C"
          fields={["temperature"]}
          sensors={[{ name: "outdoor", kind: "timeseries" }]}
          readings={[]}
          aggregates={[]}
          start={at(5)}
          end={at(10)}
          loading
        />,
      );
      expect(screen.getByText("Loading…")).toBeInTheDocument();
      expect(screen.queryByText(/no data/i)).not.toBeInTheDocument();
    });
  });

  describe("with timeseries data", () => {
    it("renders a chart with temperature readings", () => {
      render(
        <WeatherChart
          title="Temperature"
          unit="°C"
          fields={["temperature"]}
          sensors={[{ name: "outdoor", kind: "timeseries" }]}
          readings={[
            reading("outdoor", 8, 10, 15),
            reading("outdoor", 8, 14, 18),
            reading("outdoor", 9, 10, 20),
          ]}
          aggregates={[]}
          start={at(8)}
          end={at(10)}
        />,
      );

      expect(screen.getByText("Temperature")).toBeInTheDocument();
      expect(screen.queryByText(/no data/i)).not.toBeInTheDocument();
      const canvas = screen.getByRole("img");
      expect(canvas).toBeInTheDocument();
    });

    it("renders multiple sensors as separate datasets", () => {
      render(
        <WeatherChart
          title="Temperature"
          unit="°C"
          fields={["temperature"]}
          sensors={[
            { name: "outdoor", kind: "timeseries" },
            { name: "indoor", kind: "timeseries" },
          ]}
          readings={[
            reading("outdoor", 9, 10, 15),
            reading("indoor", 9, 10, 22),
          ]}
          aggregates={[]}
          start={at(9)}
          end={at(10)}
        />,
      );

      expect(screen.getByRole("img")).toBeInTheDocument();
    });
  });

  describe("with aggregate data", () => {
    it("renders aggregate bands (min/avg/max)", () => {
      render(
        <WeatherChart
          title="Temperature"
          unit="°C"
          fields={["temperature"]}
          sensors={[{ name: "station", kind: "aggregate" }]}
          readings={[]}
          aggregates={[
            aggregate("station", 7, 10, 15, 20),
            aggregate("station", 8, 12, 16, 21),
          ]}
          start={at(7)}
          end={at(9)}
        />,
      );

      expect(screen.getByRole("img")).toBeInTheDocument();
      expect(screen.queryByText(/no data/i)).not.toBeInTheDocument();
    });
  });

  describe("zoom and pan behavior", () => {
    it("accepts onRangeExtend callback for zoom/pan events", () => {
      // NOTE: testing actual zoom/pan would require mocking Chart.js pointer events,
      // which is complex and brittle. The underlying extendedRange() logic is tested
      // in chartData.test.ts. This test verifies the prop is accepted.
      const onRangeExtend = vi.fn();
      render(
        <WeatherChart
          title="Temperature"
          unit="°C"
          fields={["temperature"]}
          sensors={[{ name: "outdoor", kind: "timeseries" }]}
          readings={[reading("outdoor", 8, 10, 15)]}
          aggregates={[]}
          start={at(7)}
          end={at(9)}
          onRangeExtend={onRangeExtend}
        />,
      );

      expect(screen.getByRole("img")).toBeInTheDocument();
    });
  });
});
