// Skia can't render under jest-expo, so charts call their render prop with empty points and draw nothing.
// Axis formatters run on the first datum so their output is covered.
import type { ReactNode } from "react";

type Props = {
  data: Record<string, unknown>[];
  xKey: string;
  yKeys: string[];
  xAxis?: { formatXLabel?: (v: never) => string };
  yAxis?: { formatYLabel?: (v: never) => string }[];
  children: (args: { points: Record<string, unknown[]> }) => ReactNode;
};

export function CartesianChart({ data, xKey, yKeys, xAxis, yAxis, children }: Props) {
  const first = data[0];
  if (first) {
    xAxis?.formatXLabel?.(first[xKey] as never);
    yAxis?.[0]?.formatYLabel?.(first[yKeys[0]] as never);
  }
  return <>{children({ points: Object.fromEntries(yKeys.map((k) => [k, []])) })}</>;
}

export const Line = () => null;

export const useChartPressState = () => ({
  state: { matchedIndex: { value: -1 }, x: { position: { value: 0 } }, y: { y: { position: { value: 0 } } } },
  isActive: false,
});
