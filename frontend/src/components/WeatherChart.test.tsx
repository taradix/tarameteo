import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { WeatherChart } from "./WeatherChart";

describe("WeatherChart", () => {
  it("renders an empty state when there are no readings", () => {
    const now = new Date();
    render(
      <WeatherChart
        title="Temperature"
        unit="°C"
        field="temperature"
        sensors={[{ name: "s1", kind: "timeseries" }]}
        readings={[]}
        aggregates={[]}
        start={new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)}
        end={now}
      />,
    );
    expect(screen.getByText(/no data in range/i)).toBeInTheDocument();
  });
});
