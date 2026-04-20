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

export function useWeather(names: string[], start: string, end: string) {
  return useQueries({
    queries: names.map((name) => ({
      queryKey: ["weather", name, start, end],
      queryFn: () => api.getWeather(name, start, end),
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
