import { keepPreviousData, useQuery } from "@tanstack/react-query";
import * as Location from "expo-location";
import { Stack } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { FlatList, Pressable, StyleSheet, Switch, Text, TextInput, View } from "react-native";
import MapView, { Marker, type Region } from "react-native-maps";

import { api, KINDS, type Cluster, type SensorEntry, type SensorFilter } from "@/api";
import { COLOR } from "@/components/WeatherChart";
import { useFormat } from "@/format";
import { toggleShown, useShown } from "@/shown";

// Enough to scroll through; past that, zooming in or searching beats scrolling.
const LIMIT = 50;
const WORLD: Region = { latitude: 20, longitude: 0, latitudeDelta: 140, longitudeDelta: 360 };
// About 100 km across around you, and 20 km around a sensor picked from the list.
const NEARBY = 0.9;
const FOCUS = 0.2;

const round = (x: number) => Math.round(x * 100) / 100;
const clamp = (x: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, x));
const wrap = (lon: number) => ((((lon + 180) % 360) + 360) % 360) - 180;

// The server takes west > east as crossing the antimeridian. Three decimals (about 100 m) keep the cache key steady.
function bboxOf({ latitude, longitude, latitudeDelta, longitudeDelta }: Region) {
  const [west, east] =
    longitudeDelta >= 360 ? [-180, 180] : [wrap(longitude - longitudeDelta / 2), wrap(longitude + longitudeDelta / 2)];
  const south = clamp(latitude - latitudeDelta / 2, -90, 90);
  const north = clamp(latitude + latitudeDelta / 2, -90, 90);
  return [west, south, east, north].map((x) => +x.toFixed(3)).join(",");
}

// Web map zoom: the world is 360° wide at zoom 0, and each level halves it.
const zoomOf = (region: Region) => clamp(Math.round(Math.log2(360 / region.longitudeDelta)), 0, 22);

// Searches once typing pauses, not on every keystroke.
function useDebounced<T>(value: T, ms: number) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return debounced;
}

// Two decimals (about 1 km) is enough to sort sensors, and all the server learns about the phone.
async function currentPosition() {
  const { granted } = await Location.requestForegroundPermissionsAsync();
  if (!granted) return null;
  const { coords } = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
  return { latitude: round(coords.latitude), longitude: round(coords.longitude) };
}

export default function SensorsScreen() {
  const { t } = useFormat();
  const map = useRef<MapView>(null);
  const [filter, setFilter] = useState("");
  const [moved, setMoved] = useState<Region>();
  const [selected, setSelected] = useState<SensorEntry>();
  // Denied or failed (location off): start on the world, sorted by name.
  const position = useQuery({ queryKey: ["position"], queryFn: currentPosition, retry: false, staleTime: 10 * 60_000 });
  const here = position.data ?? undefined;
  const region = moved ?? (position.isPending ? undefined : here ? { ...here, latitudeDelta: NEARBY, longitudeDelta: NEARBY } : WORLD);
  const bbox = region && bboxOf(region);
  const zoom = region && zoomOf(region);
  const q = useDebounced(filter.trim(), 300) || undefined;

  // Searching looks everywhere; otherwise the list follows the map.
  const params: SensorFilter = { q, bbox: q ? undefined : bbox, ...here, limit: LIMIT };
  const sensorsQuery = useQuery({
    queryKey: ["sensors", params],
    queryFn: () => api.listSensors(params),
    enabled: region !== undefined,
    // Keep the list while the next one loads, instead of flashing empty on every pan or keystroke.
    placeholderData: keepPreviousData,
  });
  const clustersQuery = useQuery({
    queryKey: ["clusters", bbox, zoom],
    queryFn: () => api.listClusters(bbox!, zoom!),
    enabled: region !== undefined,
    placeholderData: keepPreviousData,
  });

  const sensors = (sensorsQuery.data?.sensors ?? []).filter((s) => KINDS.includes(s.kind));
  const error = sensorsQuery.error ?? clustersQuery.error;

  const focus = (s: SensorEntry) => {
    setSelected(s);
    map.current?.animateToRegion({ latitude: s.latitude, longitude: s.longitude, latitudeDelta: FOCUS, longitudeDelta: FOCUS });
  };
  // Cells are a quarter of the view, so zooming in twice splits the cluster.
  // ponytail: sensors sharing a spot stay one cluster at any zoom; spread them out if that happens.
  const expand = (c: Cluster) =>
    map.current?.animateToRegion({
      latitude: c.latitude,
      longitude: c.longitude,
      latitudeDelta: region!.latitudeDelta / 4,
      longitudeDelta: region!.longitudeDelta / 4,
    });

  return (
    <View style={styles.screen}>
      <Stack.Screen options={{ title: t("sensors.title") }} />
      <TextInput
        style={styles.search}
        placeholder={t("sensors.search")}
        value={filter}
        onChangeText={setFilter}
        autoCorrect={false}
      />
      <View style={styles.pane}>
        {region && (
          <MapView
            ref={map}
            testID="map"
            style={StyleSheet.absoluteFill}
            initialRegion={region}
            showsUserLocation={here !== undefined}
            onRegionChangeComplete={(r) => setMoved(r)}
            // iOS also reports pin taps to the map.
            onPress={(e) => e.nativeEvent.action !== "marker-press" && setSelected(undefined)}
          >
            {clustersQuery.data?.clusters.map((c) =>
              c.sensor ? (
                KINDS.includes(c.sensor.kind) && <SensorPin key={`${c.sensor.kind}:${c.sensor.name}`} sensor={c.sensor} onPress={setSelected} />
              ) : (
                <Marker
                  key={`${c.latitude},${c.longitude}`}
                  coordinate={c}
                  accessibilityLabel={t("sensors.cluster", { count: c.count })}
                  onPress={() => expand(c)}
                >
                  <View style={styles.cluster}>
                    <Text style={styles.clusterText}>{c.count}</Text>
                  </View>
                </Marker>
              ),
            )}
          </MapView>
        )}
        {selected && (
          <View style={styles.card}>
            <Row sensor={selected} />
          </View>
        )}
      </View>
      <FlatList
        style={styles.pane}
        data={sensors}
        keyExtractor={(s) => `${s.kind}:${s.name}`}
        keyboardShouldPersistTaps="handled"
        ListHeaderComponent={
          <>
            {!here && !position.isPending && <Text style={styles.message}>{t("sensors.noLocation")}</Text>}
            {error && <Text style={styles.message}>{String(error)}</Text>}
          </>
        }
        ListFooterComponent={
          sensorsQuery.data?.truncated ? (
            <Text style={styles.message}>{t(here ? "sensors.truncatedNear" : "sensors.truncated", { count: LIMIT })}</Text>
          ) : undefined
        }
        ListEmptyComponent={sensorsQuery.isSuccess ? <Text style={styles.message}>{t("dashboard.empty")}</Text> : undefined}
        renderItem={({ item }) => <Row sensor={item} onPress={() => focus(item)} />}
      />
    </View>
  );
}

function SensorPin({ sensor, onPress }: { sensor: SensorEntry; onPress: (s: SensorEntry) => void }) {
  const shown = useShown();
  return (
    <Marker
      coordinate={sensor}
      accessibilityLabel={sensor.name}
      pinColor={shown.has(sensor.name) ? COLOR : undefined}
      onPress={() => onPress(sensor)}
    />
  );
}

function Row({ sensor, onPress }: { sensor: SensorEntry; onPress?: () => void }) {
  const { t, num } = useFormat();
  const shown = useShown();
  return (
    <View style={styles.row}>
      <Pressable style={styles.label} onPress={onPress} disabled={!onPress}>
        <Text style={styles.name}>{sensor.name}</Text>
        {sensor.distance_km != null && (
          <Text style={styles.distance}>{num(sensor.distance_km, sensor.distance_km < 10 ? 1 : 0)} km</Text>
        )}
      </Pressable>
      <Switch
        accessibilityLabel={t("sensors.toggle", { name: sensor.name })}
        value={shown.has(sensor.name)}
        onValueChange={() => toggleShown(sensor.name)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  search: { margin: 12, padding: 10, borderRadius: 8, borderWidth: 1, borderColor: "#ccc" },
  pane: { flex: 1 },
  cluster: { minWidth: 32, padding: 6, borderRadius: 16, backgroundColor: COLOR, alignItems: "center" },
  clusterText: { color: "#fff", fontWeight: "600" },
  card: { position: "absolute", left: 8, right: 8, bottom: 8, borderRadius: 8, backgroundColor: "#fff", elevation: 4, shadowOpacity: 0.2, shadowRadius: 4 },
  message: { padding: 16, textAlign: "center" },
  row: { flexDirection: "row", alignItems: "center", padding: 16, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: "#ccc" },
  label: { flex: 1 },
  name: { fontSize: 17 },
  distance: { fontSize: 13, color: "#888", marginTop: 2 },
});
