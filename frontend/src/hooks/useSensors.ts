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

// end=null means live mode: fetch up to now() at query time so new readings appear
export function useWeather(names: string[], start: string, end: Date | null) {
  return useQueries({
    queries: names.map((name) => ({
      queryKey: end ? ["weather", name, start, end.toISOString()] : ["weather", name, start],
      queryFn: () => api.getWeather(name, start, (end ?? new Date()).toISOString()),
      refetchInterval: REFETCH_MS,
    })),
    combine: (results) => ({
      data: results.flatMap<WeatherReading>((r) => r.data ?? []),
      isLoading: results.some((r) => r.isLoading),
      isFetching: results.some((r) => r.isFetching),
      error: results.find((r) => r.error)?.error ?? null,
    }),
  });
}
