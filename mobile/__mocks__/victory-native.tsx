// Skia can't render under jest-expo, so charts call their render prop with empty points and draw nothing.
// Axis formatters run on the first datum so their output is covered.
import type { ReactNode } from "react";

type Props = {
  data: Record<string, unknown>[];
  xKey: string;
  yKeys: string[];
  xAxis?: { formatXLabel?: (v: never) => string };
  yAxis?: { formatYLabel?: (v: never) => string }[];
  children: (args: { points: Record<string, unknown[]>; chartBounds: object }) => ReactNode;
};

export function CartesianChart({ data, xKey, yKeys, xAxis, yAxis, children }: Props) {
  const first = data[0];
  if (first) {
    xAxis?.formatXLabel?.(first[xKey] as never);
    yAxis?.[0]?.formatYLabel?.(first[yKeys[0]] as never);
  }
  const points = Object.fromEntries(yKeys.map((k) => [k, []]));
  return <>{children({ points, chartBounds: { left: 0, right: 0, top: 0, bottom: 0 } })}</>;
}

export const Line = () => null;
export const AreaRange = () => null;
export const BarGroup = Object.assign(() => null, { Bar: () => null });

export const useChartPressState = (init: { y: Record<string, number> }) => ({
  state: {
    matchedIndex: { value: -1 },
    x: { position: { value: 0 } },
    y: Object.fromEntries(Object.keys(init.y).map((k) => [k, { position: { value: 0 } }])),
  },
  isActive: false,
});
