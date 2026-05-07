import { useMemo } from "react";
import { useQueryStates, parseAsArrayOf, parseAsString, parseAsIsoDateTime } from "nuqs";
import { startOfToday, startOfYesterday, subDays } from "date-fns";

function computeRange(
  preset: string,
  customStart: Date | null,
  customEnd: Date | null,
): { start: Date; end: Date | null } {
  switch (preset) {
    case "live":      return { start: startOfToday(),              end: null             };
    case "yesterday": return { start: startOfYesterday(),           end: startOfToday()   };
    case "7d":        return { start: subDays(startOfToday(), 7),  end: null             };
    case "30d":       return { start: subDays(startOfToday(), 30), end: null             };
    default:          return { start: customStart ?? startOfToday(), end: customEnd ?? null };
  }
}

export function useDashboardState() {
  const [params, setParams] = useQueryStates({
    sensors: parseAsArrayOf(parseAsString).withDefault([]),
    preset: parseAsString.withDefault("live"),
    start: parseAsIsoDateTime,
    end: parseAsIsoDateTime,
  });

  const { start, end } = useMemo(
    () => computeRange(params.preset, params.start, params.end),
    [params.preset, params.start, params.end],
  );

  return [{ sensors: params.sensors, preset: params.preset, start, end }, setParams] as const;
}
