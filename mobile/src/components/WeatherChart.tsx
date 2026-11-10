import { Circle, matchFont } from "@shopify/react-native-skia";
import { type ReactNode, useState } from "react";
import { Platform, StyleSheet, Text, View } from "react-native";
import { useAnimatedReaction } from "react-native-reanimated";
import { scheduleOnRN } from "react-native-worklets";
import { CartesianChart, type CartesianChartRenderArg, useChartPressState } from "victory-native";

import { useFormat } from "@/format";

export const COLOR = "#1976d2";
const font = matchFont({ fontFamily: Platform.select({ ios: "Helvetica", default: "sans-serif" }), fontSize: 11 });

export type Row = { x: number; [key: string]: number | null | undefined };

type Props = {
  title: string;
  hours: number;
  data: Row[];
  yKeys: string[];
  // Text for one row, shown above the chart.
  label: (row: Row) => string;
  // One row per day: label with the date only.
  daily?: boolean;
  // Bars start at zero and need room for the first and last ones.
  bars?: boolean;
  children: (args: CartesianChartRenderArg<Row, string>) => ReactNode;
};

// Shows the latest row, or the pressed one while the user holds a finger on the chart.
export function WeatherChart({ title, hours, data, yKeys, label, daily, bars, children }: Props) {
  const { num, tick, when, day } = useFormat();
  const { state, isActive } = useChartPressState({ x: 0, y: Object.fromEntries(yKeys.map((k) => [k, 0])) });
  const [pressed, setPressed] = useState(-1);
  useAnimatedReaction(
    () => state.matchedIndex.value,
    (index) => scheduleOnRN(setPressed, index),
  );

  const shown = (isActive && data[pressed]) || data.at(-1);
  return (
    <View style={styles.card}>
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.value}>{shown ? `${label(shown)} · ${daily ? day(shown.x) : when(shown.x)}` : " "}</Text>
      <View style={styles.chart}>
        <CartesianChart
          data={data}
          xKey="x"
          yKeys={yKeys}
          chartPressState={state}
          domain={bars ? { y: [0] } : undefined}
          domainPadding={bars ? { left: 12, right: 12 } : undefined}
          xAxis={{ font, tickCount: 4, formatXLabel: (ms) => tick(ms, hours) }}
          yAxis={[{ font, formatYLabel: (v) => num(v, 0) }]}
        >
          {(args) => (
            <>
              {children(args)}
              {isActive && <Circle cx={state.x.position} cy={state.y[yKeys[0]].position} r={5} color={COLOR} />}
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
