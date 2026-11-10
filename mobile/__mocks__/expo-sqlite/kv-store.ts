// The native SQLite module doesn't exist under Jest; the app only needs the sync key-value calls.
const items = new Map<string, string>();

export const Storage = {
  getItemSync: (key: string) => items.get(key) ?? null,
  setItemSync: (key: string, value: string) => void items.set(key, value),
};
