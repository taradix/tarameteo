import { describe, expect, it } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { useSensorList, useSensorSearch, useWeather } from "./useSensors";
import { queryWrapper, stubEventSource, stubFetch } from "../test/utils";
import type { SensorRef } from "../types";

const sensors: SensorRef[] = [
  { name: "ts", kind: "timeseries" },
  { name: "agg", kind: "aggregate" },
];
const reading = (sensor: string, timestamp: string) => ({ sensor, timestamp, temperature: 1 });

describe("useSensorList", () => {
  it("fetches the selected sensors by sorted name", async () => {
    const fetch = stubFetch({ "/api/sensors": { sensors } });
    const { result } = renderHook(() => useSensorList(["ts", "agg"]), { wrapper: queryWrapper() });
    await waitFor(() => expect(result.current.data).toEqual({ sensors }));
    expect(fetch).toHaveBeenCalledWith("/api/sensors?names=agg&names=ts", undefined);
  });

  it("doesn't fetch without a selection", () => {
    const fetch = stubFetch({});
    renderHook(() => useSensorList([]), { wrapper: queryWrapper() });
    expect(fetch).not.toHaveBeenCalled();
  });
});

describe("useSensorSearch", () => {
  it("searches the trimmed input once typing pauses", async () => {
    const fetch = stubFetch({ "/api/sensors": { sensors } });
    const { result, rerender } = renderHook(({ input }) => useSensorSearch(input, 20), {
      wrapper: queryWrapper(),
      initialProps: { input: "" },
    });
    rerender({ input: " t" });
    rerender({ input: " ts " });
    await waitFor(() => expect(result.current.data).toEqual({ sensors }));
    expect(fetch).toHaveBeenCalledExactlyOnceWith("/api/sensors?q=ts&limit=20", undefined);
  });
});

describe("useWeather", () => {
  it("fetches each sensor by kind for a fixed range without streaming", async () => {
    const fetch = stubFetch({
      "/api/sensors/ts/weather": [reading("ts", "t1")],
      "/api/sensors/agg/weather/aggregate": [reading("agg", "t2")],
    });
    const sources = stubEventSource();
    const end = new Date("2026-01-02T00:00:00Z");
    const { result } = renderHook(() => useWeather(sensors, "2026-01-01T00:00:00Z", end), {
      wrapper: queryWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.readings).toEqual([reading("ts", "t1")]);
    expect(result.current.aggregates).toEqual([reading("agg", "t2")]);
    expect(result.current.error).toBeNull();
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining("end=2026-01-02T00%3A00%3A00.000Z"), undefined);
    expect(sources).toHaveLength(0);
  });

  it("reports a failed request as an error", async () => {
    stubFetch({ "/api/sensors/agg/weather/aggregate": [] });
    stubEventSource();
    const { result } = renderHook(() => useWeather(sensors, "start", new Date()), { wrapper: queryWrapper() });
    await waitFor(() => expect(result.current.error).toMatchObject({ message: "404 Not Found" }));
  });

  it("streams only timeseries in live mode, skips bad frames, and closes streams on unmount", async () => {
    stubFetch({
      "/api/sensors/ts/weather": [reading("ts", "t1")],
      "/api/sensors/agg/weather/aggregate": [],
    });
    const sources = stubEventSource();
    const { result, unmount } = renderHook(() => useWeather(sensors, "start", null), {
      wrapper: queryWrapper(),
    });

    await waitFor(() => expect(result.current.readings).toHaveLength(1));
    expect(sources.map((s) => s.url)).toEqual(["/api/sensors/ts/weather/stream"]);

    act(() => {
      sources[0].onmessage?.(new MessageEvent("message", { data: "not json" }));
      sources[0].emit(reading("ts", "t2"));
    });
    expect(result.current.readings).toEqual([reading("ts", "t1"), reading("ts", "t2")]);

    unmount();
    expect(sources.every((s) => s.closed)).toBe(true);
  });

  it("drops streamed readings when the range moves", async () => {
    stubFetch({ "/api/sensors/ts/weather": [] });
    const sources = stubEventSource();
    const { result, rerender } = renderHook(({ start }) => useWeather(sensors, start, null), {
      wrapper: queryWrapper(),
      initialProps: { start: "a" },
    });
    act(() => sources[0].emit(reading("ts", "t1")));
    expect(result.current.readings).toHaveLength(1);

    rerender({ start: "b" });
    expect(result.current.readings).toEqual([]);
    expect(sources[0].closed).toBe(true);
    expect(sources).toHaveLength(2);
  });

  it("does not stream without sensors", () => {
    stubFetch({});
    const sources = stubEventSource();
    renderHook(() => useWeather([], "start", null), { wrapper: queryWrapper() });
    expect(sources).toHaveLength(0);
  });
});
