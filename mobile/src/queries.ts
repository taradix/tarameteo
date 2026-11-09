import { api } from "@/api";

// Sensors report hourly and MELCCFP daily; pull to refresh covers the impatient.
export const REFETCH_MS = 5 * 60_000;

const hoursAgo = (hours: number) => new Date(Date.now() - hours * 3600_000).toISOString();

// Shared by the cards and the detail screen so opening a sensor reuses the card's 24 h data.
export const weatherQuery = (name: string, hours: number) => ({
  queryKey: ["weather", name, hours],
  queryFn: () => api.getWeather(name, hoursAgo(hours)),
  refetchInterval: REFETCH_MS,
});

export const aggregateQuery = (name: string, hours: number) => ({
  queryKey: ["aggregate", name, hours],
  queryFn: () => api.getWeatherAggregate(name, hoursAgo(hours)),
  refetchInterval: REFETCH_MS,
});
