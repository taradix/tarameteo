// Skia can't render under jest-expo, so charts call their render prop with empty points and draw nothing.
import type { ReactNode } from "react";

type Props = { yKeys: string[]; children: (args: { points: Record<string, unknown[]> }) => ReactNode };

export function CartesianChart({ yKeys, children }: Props) {
  return <>{children({ points: Object.fromEntries(yKeys.map((k) => [k, []])) })}</>;
}

export const Line = () => null;
