import { useEffect, useMemo, useState } from "react";
import {
  keepPreviousData, useQueries, useQuery, useQueryClient, type Query, type UseQueryResult,
} from "@tanstack/react-query";
import { api, type SensorFilter } from "../api";
import type { SensorRef, WeatherReading } from "../types";

const REFETCH_MS = 30_000;
const SEARCH_DEBOUNCE_MS = 300;

// Selected sensors by name: their kinds decide which endpoint charts them.
export function useSensorList(names: string[]) {
  // Sorted so the cache key doesn't depend on the order sensors were picked in.
  const filter: SensorFilter = { names: [...names].sort() };
  return useQuery({
    queryKey: ["sensors", filter],
    queryFn: () => api.listSensors(filter),
    enabled: names.length > 0,
    refetchInterval: REFETCH_MS,
  });
}

// Name suggestions, searched once typing pauses.
export function useSensorSearch(input: string, limit: number) {
  const q = useDebounced(input.trim(), SEARCH_DEBOUNCE_MS);
  const filter: SensorFilter = { q, limit };
  return useQuery({
    queryKey: ["sensors", filter],
    queryFn: () => api.listSensors(filter),
    enabled: q.length > 0,
    // Keep the suggestions while the next search loads.
    placeholderData: keepPreviousData,
  });
}

function useDebounced<T>(value: T, ms: number) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return debounced;
}

// Module-level so useQueries can memoize the combined result between renders.
function combine<T>(results: UseQueryResult<T[]>[]) {
  return {
    data: results.flatMap((r) => r.data ?? []),
    isLoading: results.some((r) => r.isLoading),
    error: results.find((r) => r.error)?.error ?? null,
  };
}

const rangeKey = (prefix: string, name: string, start: string, end: Date | null) =>
  end ? [prefix, name, start, end.toISOString()] : [prefix, name, start];

// One query per sensor over [start, end), or [start, now) when end is null.
// Polling stops after the first fetch past end: a range that has ended doesn't
// change, but one ending in the future still fills in.
function useRangeQueries<T>(
  prefix: string,
  fetcher: (name: string, start: string, end?: string) => Promise<T[]>,
  sensors: SensorRef[],
  start: string,
  end: Date | null,
  poll: boolean,
) {
  return useQueries({
    queries: sensors.map((s) => ({
      queryKey: rangeKey(prefix, s.name, start, end),
      queryFn: () => fetcher(s.name, start, end?.toISOString()),
      refetchInterval: (query: Query<T[]>) =>
        poll && (end === null || query.state.dataUpdatedAt <= end.getTime()) ? REFETCH_MS : false,
    })),
    combine: combine<T>,
  });
}

// end=null means live mode. Live timeseries stream new readings into their
// query; aggregates poll instead, since their stream repeats the day in progress
// each hour and appending it would chart that day twice.
export function useWeather(sensors: SensorRef[], start: string, end: Date | null) {
  const queryClient = useQueryClient();
  const live = end === null;
  const tsSensors = useMemo(() => sensors.filter((s) => s.kind === "timeseries"), [sensors]);
  const aggSensors = useMemo(() => sensors.filter((s) => s.kind === "aggregate"), [sensors]);

  const ts = useRangeQueries("weather", api.getWeather, tsSensors, start, end, !live);
  const agg = useRangeQueries("weather_aggregate", api.getWeatherAggregate, aggSensors, start, end, true);

  // Streamed readings live in each sensor's cached range, so restarting the
  // streams when a sensor is added keeps the others', and moving the range
  // drops them with its old query.
  // NOTE: a live preset's start doesn't slide with time, so a tab left open for
  // days keeps every streamed reading; recompute start on a timer if that matters.
  useEffect(() => {
    if (!live || tsSensors.length === 0) {
      return;
    }

    const sources = tsSensors.map((s) => {
      const es = new EventSource(api.streamUrl(s.name));
      es.onmessage = (e: MessageEvent<string>) => {
        let reading: WeatherReading;
        try {
          reading = JSON.parse(e.data) as WeatherReading;
        } catch {
          return;
        }
        queryClient.setQueryData<WeatherReading[]>(
          rangeKey("weather", s.name, start, null),
          (prev) => [...(prev ?? []), reading],
        );
      };
      return es;
    });

    return () => sources.forEach((es) => es.close());
  }, [queryClient, tsSensors, live, start]);

  return {
    readings: ts.data,
    aggregates: agg.data,
    isLoading: ts.isLoading || agg.isLoading,
    error: ts.error ?? agg.error,
  };
}
