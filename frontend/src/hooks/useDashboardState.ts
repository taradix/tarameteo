import { useQueryStates, parseAsArrayOf, parseAsString, parseAsIsoDateTime } from "nuqs";
import { subDays } from "date-fns";

const defaultStart = () => subDays(new Date(), 7);
const defaultEnd = () => new Date();

export function useDashboardState() {
  return useQueryStates({
    sensors: parseAsArrayOf(parseAsString).withDefault([]),
    start: parseAsIsoDateTime.withDefault(defaultStart()),
    end: parseAsIsoDateTime.withDefault(defaultEnd()),
  });
}
