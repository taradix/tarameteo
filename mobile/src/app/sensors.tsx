import { useQuery } from "@tanstack/react-query";
import * as Location from "expo-location";
import { Stack } from "expo-router";
import { useState } from "react";
import { FlatList, Pressable, StyleSheet, Switch, Text, TextInput, View } from "react-native";

import { api, KINDS, type Near } from "@/api";
import { COLOR } from "@/components/WeatherChart";
import { useFormat } from "@/format";
import { toggleShown, useShown } from "@/shown";

const RADII = [10, 50, 200, null];
const round = (x: number) => Math.round(x * 100) / 100;

// Two decimals (about 1 km) is enough to sort sensors, and all the server learns about the phone.
async function currentPosition() {
  const { granted } = await Location.requestForegroundPermissionsAsync();
  if (!granted) return null;
  const { coords } = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
  return { latitude: round(coords.latitude), longitude: round(coords.longitude) };
}

export default function SensorsScreen() {
  const { t, num } = useFormat();
  const shown = useShown();
  const [radius, setRadius] = useState<number | null>(50);
  const [filter, setFilter] = useState("");
  // Denied or failed (location off): fall back to every sensor by name.
  const position = useQuery({ queryKey: ["position"], queryFn: currentPosition, retry: false, staleTime: 10 * 60_000 });
  const here = position.data ?? undefined;
  const near: Near | undefined = here && (radius ? { ...here, radius } : here);
  const sensorsQuery = useQuery({
    queryKey: near ? ["sensors", near] : ["sensors"],
    queryFn: () => api.listSensors(near),
    enabled: !position.isPending,
  });

  const needle = filter.trim().toLocaleLowerCase();
  const sensors = (sensorsQuery.data?.sensors ?? []).filter(
    (s) => KINDS.includes(s.kind) && s.name.toLocaleLowerCase().includes(needle),
  );
  if (!here) sensors.sort((a, b) => a.name.localeCompare(b.name));

  return (
    <FlatList
      data={sensors}
      keyExtractor={(s) => `${s.kind}:${s.name}`}
      keyboardShouldPersistTaps="handled"
      ListHeaderComponent={
        <>
          <Stack.Screen options={{ title: t("sensors.title") }} />
          <TextInput
            style={styles.search}
            placeholder={t("sensors.search")}
            value={filter}
            onChangeText={setFilter}
            autoCorrect={false}
          />
          {here ? (
            <View style={styles.radii} accessibilityRole="tablist">
              {RADII.map((r) => (
                <Pressable
                  key={r ?? "all"}
                  accessibilityRole="tab"
                  accessibilityState={{ selected: r === radius }}
                  onPress={() => setRadius(r)}
                  style={[styles.radius, r === radius && styles.selected]}
                >
                  <Text style={r === radius && styles.selectedText}>{r ? `${r} km` : t("sensors.all")}</Text>
                </Pressable>
              ))}
            </View>
          ) : position.isPending ? null : (
            <Text style={styles.message}>{t("sensors.noLocation")}</Text>
          )}
          {sensorsQuery.error && <Text style={styles.message}>{String(sensorsQuery.error)}</Text>}
        </>
      }
      ListEmptyComponent={sensorsQuery.isSuccess ? <Text style={styles.message}>{t("dashboard.empty")}</Text> : undefined}
      renderItem={({ item }) => (
        <View style={styles.row}>
          <View style={styles.label}>
            <Text style={styles.name}>{item.name}</Text>
            {item.distance_km != null && (
              <Text style={styles.distance}>{num(item.distance_km, item.distance_km < 10 ? 1 : 0)} km</Text>
            )}
          </View>
          <Switch
            accessibilityLabel={t("sensors.toggle", { name: item.name })}
            value={shown.has(item.name)}
            onValueChange={() => toggleShown(item.name)}
          />
        </View>
      )}
    />
  );
}

const styles = StyleSheet.create({
  search: { margin: 16, marginBottom: 0, padding: 10, borderRadius: 8, borderWidth: 1, borderColor: "#ccc" },
  radii: { flexDirection: "row", gap: 8, padding: 16 },
  radius: { paddingHorizontal: 14, paddingVertical: 6, borderRadius: 16, borderWidth: 1, borderColor: "#ccc" },
  selected: { backgroundColor: COLOR, borderColor: COLOR },
  selectedText: { color: "#fff" },
  message: { padding: 16, textAlign: "center" },
  row: { flexDirection: "row", alignItems: "center", padding: 16, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: "#ccc" },
  label: { flex: 1 },
  name: { fontSize: 17 },
  distance: { fontSize: 13, color: "#888", marginTop: 2 },
});
