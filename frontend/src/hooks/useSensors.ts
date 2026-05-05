import { useEffect, useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type { WeatherReading } from "../types";

const REFETCH_MS = 30_000;

export function useSensorList() {
  return useQuery({
    queryKey: ["sensors"],
    queryFn: api.listSensors,
    refetchInterval: REFETCH_MS,
  });
}

export function useSensorInfo(name: string | null) {
  return useQuery({
    queryKey: ["sensor", name],
    queryFn: () => api.getSensor(name!),
    enabled: !!name,
    refetchInterval: REFETCH_MS,
  });
}

// end=null means live mode: initial REST fetch + SSE for incremental updates.
export function useWeather(names: string[], start: string, end: Date | null) {
  const queries = useQueries({
    queries: names.map((name) => ({
      queryKey: end ? ["weather", name, start, end.toISOString()] : ["weather", name, start],
      queryFn: () => api.getWeather(name, start, (end ?? new Date()).toISOString()),
      refetchInterval: end ? REFETCH_MS : false,
    })),
    combine: (results) => ({
      data: results.flatMap<WeatherReading>((r) => r.data ?? []),
      isLoading: results.some((r) => r.isLoading),
      isFetching: results.some((r) => r.isFetching),
      error: results.find((r) => r.error)?.error ?? null,
    }),
  });

  const [liveReadings, setLiveReadings] = useState<WeatherReading[]>([]);

  useEffect(() => {
    if (end !== null || names.length === 0) {
      return;
    }

    const sources = names.map((name) => {
      const es = new EventSource(`/api/sensors/${encodeURIComponent(name)}/weather/stream`);
      es.onmessage = (e: MessageEvent) => {
        const reading = JSON.parse(e.data as string) as WeatherReading;
        setLiveReadings((prev) => [...prev, reading]);
      };
      return es;
    });

    return () => {
      sources.forEach((es) => es.close());
      setLiveReadings([]);
    };
  }, [names, end]);

  return {
    data: [...queries.data, ...liveReadings],
    isLoading: queries.isLoading,
    isFetching: queries.isFetching,
    error: queries.error,
  };
}
