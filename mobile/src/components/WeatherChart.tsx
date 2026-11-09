import { Circle, matchFont } from "@shopify/react-native-skia";
import { useState } from "react";
import { Platform, StyleSheet, Text, View } from "react-native";
import { useAnimatedReaction } from "react-native-reanimated";
import { scheduleOnRN } from "react-native-worklets";
import { CartesianChart, Line, useChartPressState } from "victory-native";

import { useFormat } from "@/format";

const COLOR = "#1976d2";
const font = matchFont({ fontFamily: Platform.select({ ios: "Helvetica", default: "sans-serif" }), fontSize: 11 });

export type Point = { x: number; y: number };

type Props = { title: string; unit: string; digits: number; hours: number; data: Point[] };

// Shows the latest value, or the pressed one while the user holds a finger on the chart.
export function WeatherChart({ title, unit, digits, hours, data }: Props) {
  const { num, tick, when } = useFormat();
  const { state, isActive } = useChartPressState({ x: 0, y: { y: 0 } });
  const [pressed, setPressed] = useState(-1);
  useAnimatedReaction(
    () => state.matchedIndex.value,
    (index) => scheduleOnRN(setPressed, index),
  );

  const shown = (isActive && data[pressed]) || data.at(-1);
  return (
    <View style={styles.card}>
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.value}>
        {shown ? `${num(shown.y, digits)} ${unit} · ${when(shown.x)}` : " "}
      </Text>
      <View style={styles.chart}>
        <CartesianChart
          data={data}
          xKey="x"
          yKeys={["y"]}
          chartPressState={state}
          xAxis={{ font, tickCount: 4, formatXLabel: (ms) => tick(ms, hours) }}
          yAxis={[{ font, formatYLabel: (v) => num(v, 0) }]}
        >
          {({ points }) => (
            <>
              <Line points={points.y} color={COLOR} strokeWidth={2} />
              {isActive && <Circle cx={state.x.position} cy={state.y.y.position} r={5} color={COLOR} />}
            </>
          )}
        </CartesianChart>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { paddingHorizontal: 16, paddingVertical: 12 },
  title: { fontSize: 15, fontWeight: "600" },
  value: { fontSize: 13, color: "#555", marginTop: 2 },
  chart: { height: 180, marginTop: 8 },
});
