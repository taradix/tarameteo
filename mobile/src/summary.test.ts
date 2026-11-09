import { age, summarize } from "./summary";

function reading(hour: number, temperature: number, pressure: number) {
  return {
    sensor: "s1",
    timestamp: `2026-01-02T${String(hour).padStart(2, "0")}:00:00Z`,
    temperature,
    humidity: 50,
    pressure,
    latitude: 0,
    longitude: 0,
  };
}

test("summarize takes the latest reading, temperature range and 3 h trends", () => {
  const readings = [reading(0, 9, 1000), reading(1, 2, 1005), reading(3, 3, 1010), reading(4, 1, 1010.5)];

  expect(summarize(readings)).toEqual({
    latest: readings[3],
    min: 1,
    max: 9,
    temperatureTrend: "falling",
    pressureTrend: "rising",
  });
});

test("summarize treats small changes and missing history as steady", () => {
  expect(summarize([reading(0, 1, 1000), reading(3, 1.4, 1000.9)])).toMatchObject({
    temperatureTrend: undefined,
    pressureTrend: undefined,
  });
  expect(summarize([reading(2, 1, 1000), reading(3, 9, 1020)])).toMatchObject({
    temperatureTrend: undefined,
    pressureTrend: undefined,
  });
  expect(summarize([])).toBeUndefined();
});

test("age rounds down to the largest whole unit", () => {
  const now = Date.parse("2026-01-03T00:00:00Z");
  expect(age("2026-01-02T23:18:00Z", now)).toEqual({ unit: "minutes", count: 42 });
  expect(age("2026-01-02T21:30:00Z", now)).toEqual({ unit: "hours", count: 2 });
  expect(age("2026-01-01T00:00:00Z", now)).toEqual({ unit: "days", count: 2 });
  // Clock skew can put readings slightly in the future.
  expect(age("2026-01-03T00:01:00Z", now)).toEqual({ unit: "minutes", count: 0 });
});
