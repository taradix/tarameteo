import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Stack, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { AreaRange, BarGroup, Line } from "victory-native";

import type { AggregateReading, WeatherReading } from "@/api";
import { COLOR, WeatherChart } from "@/components/WeatherChart";
import { useFormat } from "@/format";
import { aggregateQuery, weatherQuery } from "@/queries";

// Daily aggregates need longer ranges than hourly readings to show anything.
const RANGES = { timeseries: [24, 7 * 24, 30 * 24], aggregate: [7 * 24, 30 * 24, 90 * 24] };
const SNOW = "#90a4ae";

const FIELDS = [
  { field: "temperature", unit: "°C", digits: 1 },
  { field: "humidity", unit: "%", digits: 0 },
  { field: "pressure", unit: "hPa", digits: 0 },
] as const;

export default function SensorScreen() {
  const { t } = useFormat();
  // The card passes the kind so the screen doesn't wait on the sensor list.
  const { name, kind } = useLocalSearchParams<{ name: string; kind?: string }>();
  const aggregate = kind === "aggregate";
  const ranges = RANGES[aggregate ? "aggregate" : "timeseries"];
  const [hours, setHours] = useState(ranges[0]);
  // Keep the current charts on screen while another range loads.
  const query = useQuery<WeatherReading[] | AggregateReading[]>({
    ...(aggregate ? aggregateQuery(name, hours) : weatherQuery(name, hours)),
    placeholderData: keepPreviousData,
  });
  const data = query.data ?? [];

  return (
    <ScrollView
      testID="sensor-scroll"
      refreshControl={<RefreshControl refreshing={query.isFetching} onRefresh={() => void query.refetch()} />}
    >
      <Stack.Screen options={{ title: name }} />
      <View style={styles.ranges} accessibilityRole="tablist">
        {ranges.map((h) => (
          <Pressable
            key={h}
            accessibilityRole="tab"
            accessibilityState={{ selected: h === hours }}
            onPress={() => setHours(h)}
            style={[styles.range, h === hours && styles.selected]}
          >
            <Text style={h === hours && styles.selectedText}>{t(`range.${h}`)}</Text>
          </Pressable>
        ))}
      </View>
      {query.error ? (
        <Text style={styles.message}>{String(query.error)}</Text>
      ) : query.data && data.length === 0 ? (
        <Text style={styles.message}>{t("chart.noData")}</Text>
      ) : aggregate ? (
        <AggregateCharts readings={data as AggregateReading[]} hours={hours} />
      ) : (
        <TimeseriesCharts readings={data as WeatherReading[]} hours={hours} />
      )}
    </ScrollView>
  );
}

function TimeseriesCharts({ readings, hours }: { readings: WeatherReading[]; hours: number }) {
  const { t, num } = useFormat();
  return FIELDS.map(({ field, unit, digits }) => (
    <WeatherChart
      key={field}
      title={t(`chart.${field}`)}
      hours={hours}
      data={readings.map((r) => ({ x: Date.parse(r.timestamp), y: r[field] }))}
      yKeys={["y"]}
      label={(row) => `${num(row.y, digits)} ${unit}`}
    >
      {({ points }) => <Line points={points.y} color={COLOR} strokeWidth={2} />}
    </WeatherChart>
  ));
}

function AggregateCharts({ readings, hours }: { readings: AggregateReading[]; hours: number }) {
  const { t, num } = useFormat();
  // Each reading covers a local day; plot it at midnight, like the web dashboard.
  const rows = readings.map((r) => ({
    x: new Date(r.timestamp).setHours(0, 0, 0, 0),
    min: r.temperature_min,
    avg: r.temperature_avg,
    max: r.temperature_max,
    rain: r.rain,
    snow: r.snow,
  }));
  return (
    <>
      <WeatherChart
        title={t("chart.temperature")}
        hours={hours}
        daily
        data={rows}
        yKeys={["avg", "min", "max"]}
        label={(row) => t("card.aggregate", { min: num(row.min, 1), avg: num(row.avg, 1), max: num(row.max, 1) })}
      >
        {({ points }) => (
          <>
            <AreaRange upperPoints={points.max} lowerPoints={points.min} color={COLOR} opacity={0.2} />
            <Line points={points.avg} color={COLOR} strokeWidth={2} />
          </>
        )}
      </WeatherChart>
      <WeatherChart
        title={t("chart.precipitation")}
        hours={hours}
        daily
        bars
        data={rows}
        yKeys={["rain", "snow"]}
        label={(row) => t("card.precipitation", { rain: num(row.rain, 1), snow: num(row.snow, 1) })}
      >
        {({ points, chartBounds }) => (
          <BarGroup chartBounds={chartBounds} betweenGroupPadding={0.3} withinGroupPadding={0.1}>
            <BarGroup.Bar points={points.rain} color={COLOR} />
            <BarGroup.Bar points={points.snow} color={SNOW} />
          </BarGroup>
        )}
      </WeatherChart>
    </>
  );
}

const styles = StyleSheet.create({
  ranges: { flexDirection: "row", gap: 8, padding: 16 },
  range: { paddingHorizontal: 14, paddingVertical: 6, borderRadius: 16, borderWidth: 1, borderColor: "#ccc" },
  selected: { backgroundColor: COLOR, borderColor: COLOR },
  selectedText: { color: "#fff" },
  message: { padding: 16, textAlign: "center" },
});
