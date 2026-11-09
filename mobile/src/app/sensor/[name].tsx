import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Stack, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";

import { WeatherChart } from "@/components/WeatherChart";
import { weatherQuery } from "@/queries";

const RANGES = [24, 7 * 24, 30 * 24];

const FIELDS = [
  { field: "temperature", unit: "°C", digits: 1 },
  { field: "humidity", unit: "%", digits: 0 },
  { field: "pressure", unit: "hPa", digits: 0 },
] as const;

export default function SensorScreen() {
  const { t } = useTranslation();
  const { name } = useLocalSearchParams<{ name: string }>();
  const [hours, setHours] = useState(24);
  // Keep the current charts on screen while another range loads.
  const query = useQuery({ ...weatherQuery(name, hours), placeholderData: keepPreviousData });
  const readings = query.data ?? [];

  return (
    <ScrollView
      testID="sensor-scroll"
      refreshControl={<RefreshControl refreshing={query.isFetching} onRefresh={() => void query.refetch()} />}
    >
      <Stack.Screen options={{ title: name }} />
      <View style={styles.ranges} accessibilityRole="tablist">
        {RANGES.map((h) => (
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
      ) : query.data && readings.length === 0 ? (
        <Text style={styles.message}>{t("chart.noData")}</Text>
      ) : (
        FIELDS.map(({ field, unit, digits }) => (
          <WeatherChart
            key={field}
            title={t(`chart.${field}`)}
            unit={unit}
            digits={digits}
            hours={hours}
            data={readings.map((r) => ({ x: Date.parse(r.timestamp), y: r[field] }))}
          />
        ))
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  ranges: { flexDirection: "row", gap: 8, padding: 16 },
  range: { paddingHorizontal: 14, paddingVertical: 6, borderRadius: 16, borderWidth: 1, borderColor: "#ccc" },
  selected: { backgroundColor: "#1976d2", borderColor: "#1976d2" },
  selectedText: { color: "#fff" },
  message: { padding: 16, textAlign: "center" },
});
