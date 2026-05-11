import { useEffect, useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type { AggregateReading, SensorEntry, WeatherReading } from "../types";

const REFETCH_MS = 30_000;

export function useSensorList() {
  return useQuery({
    queryKey: ["sensors"],
    queryFn: api.listSensors,
    refetchInterval: REFETCH_MS,
  });
}

// end=null means live mode: initial REST fetch + SSE for incremental updates.
export function useWeather(sensors: SensorEntry[], start: string, end: Date | null) {
  const tsSensors = sensors.filter((s) => s.kind === "timeseries");
  const aggSensors = sensors.filter((s) => s.kind === "aggregate");

  const tsQueries = useQueries({
    queries: tsSensors.map((s) => ({
      queryKey: end ? ["weather", s.name, start, end.toISOString()] : ["weather", s.name, start],
      queryFn: () => api.getWeather(s.name, start, (end ?? new Date()).toISOString()),
      refetchInterval: end ? REFETCH_MS : false,
    })),
    combine: (results) => ({
      data: results.flatMap<WeatherReading>((r) => r.data ?? []),
      isLoading: results.some((r) => r.isLoading),
      isFetching: results.some((r) => r.isFetching),
      error: results.find((r) => r.error)?.error ?? null,
    }),
  });

  const aggQueries = useQueries({
    queries: aggSensors.map((s) => ({
      queryKey: end
        ? ["weather_aggregate", s.name, start, end.toISOString()]
        : ["weather_aggregate", s.name, start],
      queryFn: () => api.getWeatherAggregate(s.name, start, (end ?? new Date()).toISOString()),
      refetchInterval: REFETCH_MS,
    })),
    combine: (results) => ({
      data: results.flatMap<AggregateReading>((r) => r.data ?? []),
      isLoading: results.some((r) => r.isLoading),
      isFetching: results.some((r) => r.isFetching),
      error: results.find((r) => r.error)?.error ?? null,
    }),
  });

  const [liveReadings, setLiveReadings] = useState<WeatherReading[]>([]);
  const [liveAggregates, setLiveAggregates] = useState<AggregateReading[]>([]);

  useEffect(() => {
    if (end !== null || sensors.length === 0) {
      return;
    }

    const sources = sensors.map((s) => {
      const es = new EventSource(`/api/sensors/${encodeURIComponent(s.name)}/weather/stream`);
      es.onmessage = (e: MessageEvent) => {
        if (s.kind === "timeseries") {
          const reading = JSON.parse(e.data as string) as WeatherReading;
          setLiveReadings((prev) => [...prev, reading]);
        } else {
          const reading = JSON.parse(e.data as string) as AggregateReading;
          setLiveAggregates((prev) => [...prev, reading]);
        }
      };
      return es;
    });

    return () => {
      sources.forEach((es) => es.close());
      setLiveReadings([]);
      setLiveAggregates([]);
    };
  }, [sensors, end]);

  return {
    readings: [...tsQueries.data, ...liveReadings],
    aggregates: [...aggQueries.data, ...liveAggregates],
    isLoading: tsQueries.isLoading || aggQueries.isLoading,
    isFetching: tsQueries.isFetching || aggQueries.isFetching,
    error: tsQueries.error ?? aggQueries.error,
  };
}
