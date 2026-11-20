import { useMemo } from "react";
import { useQueryStates, parseAsArrayOf, parseAsString, parseAsIsoDateTime } from "nuqs";
import { startOfToday, startOfYesterday, subDays } from "date-fns";

// Ranges by preset; end=null is live. Labels are dateRange.<preset>.
export const PRESETS: Record<string, () => { start: Date; end: Date | null }> = {
  today:     () => ({ start: startOfToday(),              end: null           }),
  yesterday: () => ({ start: startOfYesterday(),          end: startOfToday() }),
  "7d":      () => ({ start: subDays(startOfToday(), 7),  end: null           }),
  "30d":     () => ({ start: subDays(startOfToday(), 30), end: null           }),
};

export const isPreset = (preset: string) => Object.hasOwn(PRESETS, preset);

export function useDashboardState() {
  const [params, setParams] = useQueryStates({
    sensors: parseAsArrayOf(parseAsString).withDefault([]),
    hidden: parseAsArrayOf(parseAsString).withDefault([]),
    preset: parseAsString.withDefault("today"),
    start: parseAsIsoDateTime,
    end: parseAsIsoDateTime,
  });

  const { start, end } = useMemo(
    () => isPreset(params.preset)
      ? PRESETS[params.preset]()
      : { start: params.start ?? startOfToday(), end: params.end },
    [params.preset, params.start, params.end],
  );

  return [{ sensors: params.sensors, hidden: params.hidden, preset: params.preset, start, end }, setParams] as const;
}
