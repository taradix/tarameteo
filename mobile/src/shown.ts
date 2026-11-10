import { Storage } from "expo-sqlite/kv-store";
import { useSyncExternalStore } from "react";

// Names of the sensors picked for the dashboard; new sensors stay off until picked.
const KEY = "shown";
let shown: ReadonlySet<string> = new Set(JSON.parse(Storage.getItemSync(KEY) ?? "[]"));
const listeners = new Set<() => void>();

export function toggleShown(name: string) {
  const next = new Set(shown);
  if (!next.delete(name)) next.add(name);
  shown = next;
  Storage.setItemSync(KEY, JSON.stringify([...next]));
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => void listeners.delete(listener);
}

export const useShown = () => useSyncExternalStore(subscribe, () => shown);
