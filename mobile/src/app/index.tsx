import { useQueries, useQuery } from "@tanstack/react-query";
import { Link, Stack } from "expo-router";
import { useTranslation } from "react-i18next";
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";

import { api, KINDS, type AggregateReading, type SensorEntry, type WeatherReading } from "@/api";
import { COLOR } from "@/components/WeatherChart";
import { useFormat } from "@/format";
import { aggregateQuery, REFETCH_MS, weatherQuery } from "@/queries";
import { useShown } from "@/shown";
import { age, summarize, type Trend } from "@/summary";

// Two missed hourly readings.
const STALE_MS = 3 * 3600_000;

export default function Dashboard() {
  const { t } = useTranslation();
  const sensorsQuery = useQuery({
    queryKey: ["sensors"],
    queryFn: () => api.listSensors(),
    refetchInterval: REFETCH_MS,
  });

  const shown = useShown();
  const sensors = (sensorsQuery.data?.sensors ?? []).filter((s) => KINDS.includes(s.kind) && shown.has(s.name));

  const weather = useQueries({
    queries: sensors.map((s) => (s.kind === "timeseries" ? weatherQuery(s.name, 24) : aggregateQuery(s.name, 7 * 24))),
  });

  const refreshing = sensorsQuery.isFetching || weather.some((q) => q.isFetching);
  const refresh = () => {
    void sensorsQuery.refetch();
    weather.forEach((q) => void q.refetch());
  };

  if (sensorsQuery.error) {
    return <Text style={styles.message}>{String(sensorsQuery.error)}</Text>;
  }

  const choose = (
    <Link href="/sensors" asChild>
      <Pressable style={styles.choose}>
        <Text style={styles.chooseText}>{t("sensors.choose")}</Text>
      </Pressable>
    </Link>
  );

  return (
    <FlatList
      data={sensors}
      keyExtractor={(s) => s.name}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
      ListHeaderComponent={
        <Stack.Screen
          options={{ headerRight: () => <Link href="/sensors" style={styles.headerLink}>{t("sensors.title")}</Link> }}
        />
      }
      ListEmptyComponent={
        shown.size === 0 ? choose : sensorsQuery.isLoading ? undefined : <Text style={styles.message}>{t("dashboard.empty")}</Text>
      }
      renderItem={({ item, index }) => <SensorCard sensor={item} data={weather[index]?.data} fetchedAt={weather[index]?.dataUpdatedAt ?? 0} />}
    />
  );
}

function SensorCard({ sensor, data, fetchedAt }: { sensor: SensorEntry; data?: WeatherReading[] | AggregateReading[]; fetchedAt: number }) {
  const { t } = useTranslation();
  const body =
    data === undefined ? (
      <Text style={styles.time}>…</Text>
    ) : data.length === 0 ? (
      <Text style={styles.time}>{t("card.noData")}</Text>
    ) : sensor.kind === "timeseries" ? (
      <TimeseriesBody readings={data as WeatherReading[]} now={fetchedAt} />
    ) : (
      <AggregateBody reading={(data as AggregateReading[]).at(-1)!} />
    );
  return (
    <Link href={{ pathname: "/sensor/[name]", params: { name: sensor.name, kind: sensor.kind } }} asChild>
      <Pressable accessibilityRole="button">
        <View style={styles.row}>
          <Text style={styles.name}>{sensor.name}</Text>
          {body}
        </View>
      </Pressable>
    </Link>
  );
}

// Ages are relative to the last fetch, which refreshes every REFETCH_MS.
function TimeseriesBody({ readings, now }: { readings: WeatherReading[]; now: number }) {
  const { t, num } = useFormat();
  const { latest, min, max, temperatureTrend, pressureTrend } = summarize(readings)!;
  const ago = age(latest.timestamp, now);
  const stale = now - Date.parse(latest.timestamp) > STALE_MS;
  return (
    <>
      <Text style={[styles.time, stale && styles.stale]}>{t(`card.ago.${ago.unit}`, { count: ago.count })}</Text>
      <Text style={styles.value}>
        <Text style={styles.big}>{num(latest.temperature, 1)} °C</Text>
        <TrendArrow trend={temperatureTrend} />
        {"  "}
        {t("card.range", { min: num(min, 1), max: num(max, 1) })}
      </Text>
      <Text style={styles.value}>
        {num(latest.humidity, 0)} % · {num(latest.pressure, 0)} hPa
        <TrendArrow trend={pressureTrend} />
      </Text>
    </>
  );
}

function AggregateBody({ reading }: { reading: AggregateReading }) {
  const { t, num, day } = useFormat();
  return (
    <>
      {/* Daily readings: the day matters, not the time. */}
      <Text style={styles.time}>{day(Date.parse(reading.timestamp))}</Text>
      <Text style={styles.value}>
        {t("card.aggregate", {
          min: num(reading.temperature_min, 1),
          avg: num(reading.temperature_avg, 1),
          max: num(reading.temperature_max, 1),
        })}
      </Text>
      <Text style={styles.value}>{t("card.precipitation", { rain: num(reading.rain, 1), snow: num(reading.snow, 1) })}</Text>
    </>
  );
}

function TrendArrow({ trend }: { trend: Trend }) {
  const { t } = useTranslation();
  if (!trend) return null;
  return <Text accessibilityLabel={t(`card.${trend}`)}> {trend === "rising" ? "↑" : "↓"}</Text>;
}

const styles = StyleSheet.create({
  row: { padding: 16, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: "#ccc" },
  name: { fontSize: 17, fontWeight: "600" },
  big: { fontSize: 22, fontWeight: "600" },
  value: { fontSize: 15, marginTop: 4 },
  time: { fontSize: 13, color: "#888", marginTop: 2 },
  stale: { color: "#c62828" },
  message: { padding: 16, textAlign: "center" },
  choose: { alignSelf: "center", margin: 24, paddingHorizontal: 20, paddingVertical: 10, borderRadius: 20, backgroundColor: COLOR },
  chooseText: { color: "#fff", fontSize: 16 },
  headerLink: { color: COLOR, fontSize: 16 },
});
