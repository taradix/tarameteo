import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { WeatherChart } from "./WeatherChart";

describe("WeatherChart", () => {
  it("renders an empty state when there are no readings", () => {
    render(
      <WeatherChart
        title="Temperature"
        unit="°C"
        field="temperature"
        sensors={["s1"]}
        readings={[]}
      />,
    );
    expect(screen.getByText(/no data in range/i)).toBeInTheDocument();
  });
});
