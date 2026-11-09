import { describe, expect, it } from "vitest";
import { api, ApiError } from "./api";
import { stubFetch } from "./test/utils";

describe("api", () => {
  it("lists sensors", async () => {
    stubFetch({ "/api/sensors": { sensors: [{ name: "s1", kind: "timeseries" }] } });
    await expect(api.listSensors()).resolves.toEqual({ sensors: [{ name: "s1", kind: "timeseries" }] });
  });

  it("encodes the sensor name and skips undefined params", async () => {
    const fetch = stubFetch({ "/api/sensors/a%20b/weather": [] });
    await api.getWeather("a b", "2026-01-01T00:00:00Z");
    expect(fetch).toHaveBeenCalledWith("/api/sensors/a%20b/weather?start=2026-01-01T00%3A00%3A00Z");
  });

  it("passes end and limit", async () => {
    const fetch = stubFetch({ "/api/sensors/s1/weather/aggregate": [] });
    await api.getWeatherAggregate("s1", "a", "b", 10);
    expect(fetch).toHaveBeenCalledWith("/api/sensors/s1/weather/aggregate?start=a&end=b&limit=10");
  });

  it("throws ApiError with the status on failure", async () => {
    stubFetch({});
    const err = await api.listSensors().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 404, message: "404 Not Found" });
  });

  it("posts alerts as JSON", async () => {
    const fetch = stubFetch({ "/api/alerts": { status: "ok" } });
    const alert = { email: "a@b.c", sensor: "s1", field: "rain", condition: "above", threshold: 5 } as const;
    await expect(api.createAlert(alert)).resolves.toEqual({ status: "ok" });
    expect(fetch).toHaveBeenCalledWith("/api/alerts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(alert),
    });
  });

  it("throws ApiError when a post fails", async () => {
    stubFetch({});
    const alert = { email: "a@b.c", sensor: "s1", field: "rain", condition: "above", threshold: 5 } as const;
    await expect(api.createAlert(alert)).rejects.toMatchObject({ status: 404 });
  });
});
