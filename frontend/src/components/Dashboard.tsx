import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useDashboardState } from "../hooks/useDashboardState";
import { useSensorInfo, useSensorList, useWeather } from "../hooks/useSensors";
import { RangePicker } from "./DateRangePicker";
import { SensorPicker } from "./SensorPicker";
import { SensorStatistics } from "./SensorStatistics";
import { WeatherChart } from "./WeatherChart";
import LanguageToggle from "./LanguageToggle";

export function Dashboard() {
  const { t } = useTranslation();
  const [{ sensors, preset, start, end }, setParams] = useDashboardState();

  const CHARTS: { field: "temperature" | "humidity" | "pressure" | "rssi"; title: string; unit: string }[] = [
    { field: "temperature", title: t("chart.temperature"), unit: "°C" },
    { field: "humidity", title: t("chart.humidity"), unit: "%" },
    { field: "pressure", title: t("chart.pressure"), unit: "hPa" },
    { field: "rssi", title: t("chart.wifi"), unit: "dBm" },
  ];

  const sensorList = useSensorList();
  const firstSensor = sensors[0] ?? null;
  const sensorInfo = useSensorInfo(firstSensor);
  const weather = useWeather(sensors, start.toISOString(), end);

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
        <LanguageToggle />
      </header>

      <SensorPicker
        selected={sensors}
        available={sensorList.data?.sensors ?? []}
        onChange={(next) => setParams({ sensors: next })}
      />

      <RangePicker
        preset={preset}
        start={start}
        end={end}
        onChange={(changes) => setParams(changes)}
      />

      {sensorInfo.data && <SensorStatistics info={sensorInfo.data} />}

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
              key={c.field}
              title={c.title}
              unit={c.unit}
              field={c.field}
              sensors={sensors}
              readings={weather.data}
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
