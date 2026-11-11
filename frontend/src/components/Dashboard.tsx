import { useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useDashboardState } from "../hooks/useDashboardState";
import { useSensorList, useWeather } from "../hooks/useSensors";
import type { SensorRef, WeatherField } from "../types";
import { AlertsDialog } from "./AlertForm";
import { RangePicker } from "./DateRangePicker";
import { SensorPicker } from "./SensorPicker";
import { WeatherChart } from "./WeatherChart";
import LanguageToggle from "./LanguageToggle";

export function Dashboard() {
  const { t } = useTranslation();
  const [{ sensors, hidden, preset, start, end }, setParams] = useDashboardState();

  const CHARTS: { fields: WeatherField[]; title: string; unit: string }[] = [
    { fields: ["temperature"], title: t("chart.temperature"), unit: "°C" },
    { fields: ["humidity"], title: t("chart.humidity"), unit: "%" },
    { fields: ["pressure"], title: t("chart.pressure"), unit: "hPa" },
    { fields: ["rain", "snow"], title: t("chart.precipitation"), unit: "mm" },
  ];

  const sensorList = useSensorList(sensors);

  const selectedEntries = useMemo<SensorRef[]>(
    () => sensors.map(
      (name) => sensorList.data?.sensors.find((s) => s.name === name) ?? { name, kind: "timeseries" },
    ),
    [sensors, sensorList.data?.sensors],
  );

  const visibleEntries = useMemo<SensorRef[]>(
    () => selectedEntries.filter((s) => !hidden.includes(s.name)),
    [selectedEntries, hidden],
  );

  const weather = useWeather(selectedEntries, start.toISOString(), end);

  const handleRangeExtend = useCallback((newStart: Date, newEnd: Date | null) => {
    setParams({ preset: "custom", start: newStart, end: newEnd });
  }, [setParams]);

  return (
    <div className="mx-auto max-w-6xl px-4 py-6 space-y-4">
      <header className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">{t("dashboard.title")}</h1>
          <p className="text-sm text-zinc-500">
            {t("dashboard.timezone", { timezone: Intl.DateTimeFormat().resolvedOptions().timeZone })}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <AlertsDialog sensors={sensors} />
          <LanguageToggle />
        </div>
      </header>

      <SensorPicker
        selected={sensors}
        hidden={hidden}
        onChange={(next) => setParams({ sensors: next })}
        onHiddenChange={(next) => setParams({ hidden: next })}
      />

      <RangePicker
        preset={preset}
        start={start}
        end={end}
        onChange={(changes) => setParams(changes)}
      />

      {weather.error && (
        <p className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700">
          {String((weather.error as Error).message)}
        </p>
      )}

      {sensors.length === 0 ? (
        <p className="text-sm text-zinc-500">{t("dashboard.noSensors")}</p>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {CHARTS.map((c) => (
            <WeatherChart
              key={c.fields.join(",")}
              title={c.title}
              unit={c.unit}
              fields={c.fields}
              sensors={visibleEntries}
              readings={weather.readings}
              aggregates={weather.aggregates}
              start={start}
              end={end}
              onRangeExtend={handleRangeExtend}
            />
          ))}
        </div>
      )}
    </div>
  );
}
