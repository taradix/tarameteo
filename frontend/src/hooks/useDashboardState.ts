import { useQueryStates, parseAsArrayOf, parseAsString, parseAsIsoDateTime } from "nuqs";
import { subDays } from "date-fns";

export const DEFAULT_SENSORS: string[] = [];
export const DEFAULT_START = subDays(new Date(), 7);
export const DEFAULT_END = new Date();

export function useDashboardState() {
  return useQueryStates({
    sensors: parseAsArrayOf(parseAsString).withDefault(DEFAULT_SENSORS),
    start: parseAsIsoDateTime.withDefault(DEFAULT_START),
    end: parseAsIsoDateTime.withDefault(DEFAULT_END),
  });
}
