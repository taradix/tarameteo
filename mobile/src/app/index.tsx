import { useQueries, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { FlatList, RefreshControl, StyleSheet, Text, View } from "react-native";

import { api, type WeatherReading } from "@/api";

const REFETCH_MS = 30_000;

export default function Dashboard() {
  const { t } = useTranslation();
  const sensorsQuery = useQuery({
    queryKey: ["sensors"],
    queryFn: api.listSensors,
    refetchInterval: REFETCH_MS,
  });

  // ponytail: /weather/latest only covers timeseries sensors; aggregate ones need their own endpoint.
  const names = (sensorsQuery.data?.sensors ?? []).filter((s) => s.kind === "timeseries").map((s) => s.name);

  const latest = useQueries({
    queries: names.map((name) => ({
      queryKey: ["latest", name],
      queryFn: () => api.getLatest(name),
      refetchInterval: REFETCH_MS,
    })),
  });

  const refreshing = sensorsQuery.isFetching || latest.some((q) => q.isFetching);
  const refresh = () => {
    void sensorsQuery.refetch();
    latest.forEach((q) => void q.refetch());
  };

  if (sensorsQuery.error) {
    return <Text style={styles.message}>{String(sensorsQuery.error)}</Text>;
  }

  return (
    <FlatList
      data={names}
      keyExtractor={(name) => name}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
      ListEmptyComponent={sensorsQuery.isLoading ? undefined : <Text style={styles.message}>{t("dashboard.empty")}</Text>}
      renderItem={({ item, index }) => <SensorRow name={item} reading={latest[index]?.data} />}
    />
  );
}

function SensorRow({ name, reading }: { name: string; reading?: WeatherReading }) {
  const { i18n } = useTranslation();
  return (
    <View style={styles.row}>
      <Text style={styles.name}>{name}</Text>
      {reading ? (
        <>
          <Text style={styles.value}>
            {reading.temperature.toFixed(1)} °C · {reading.humidity.toFixed(0)} % · {reading.pressure.toFixed(0)} hPa
          </Text>
          <Text style={styles.time}>{new Date(reading.timestamp).toLocaleString(i18n.language)}</Text>
        </>
      ) : (
        <Text style={styles.time}>…</Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { padding: 16, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: "#ccc" },
  name: { fontSize: 17, fontWeight: "600" },
  value: { fontSize: 15, marginTop: 4 },
  time: { fontSize: 13, color: "#888", marginTop: 2 },
  message: { padding: 16, textAlign: "center" },
});
