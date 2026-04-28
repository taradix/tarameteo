import { useRef, useState, type KeyboardEvent } from "react";

interface Props {
  selected: string[];
  available: string[];
  onChange: (sensors: string[]) => void;
}

export function SensorPicker({ selected, available, onChange }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [input, setInput] = useState("");
  const [focused, setFocused] = useState(false);

  const add = () => {
    const name = input.trim();
    if (!name || selected.includes(name)) return;
    onChange([...selected, name]);
    setInput("");
    inputRef.current?.blur();
  };

  const remove = (name: string) => onChange(selected.filter((s) => s !== name));

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") add();
  };

  const suggestions = focused ? available.filter((s) => !selected.includes(s)) : [];

  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <h2 className="mb-3 text-lg font-semibold">Sensors</h2>

      <div className="flex gap-2">
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          placeholder="Add sensor by name…"
          className="flex-1 rounded border border-zinc-300 bg-white px-2 py-1 dark:border-zinc-700 dark:bg-zinc-900"
          list="sensor-suggestions"
        />
        <datalist id="sensor-suggestions">
          {suggestions.map((s) => <option key={s} value={s} />)}
        </datalist>
        <button
          type="button"
          onClick={add}
          disabled={!input.trim()}
          className="rounded bg-blue-600 px-3 py-1 text-white disabled:opacity-50"
        >
          Add
        </button>
      </div>

      {selected.length === 0 ? (
        <p className="mt-3 text-sm text-zinc-500">No sensors selected.</p>
      ) : (
        <ul className="mt-3 flex flex-wrap gap-2">
          {selected.map((name) => (
            <li
              key={name}
              className="flex items-center gap-2 rounded-full bg-zinc-100 px-3 py-1 text-sm dark:bg-zinc-800"
            >
              <span>{name}</span>
              <button
                type="button"
                onClick={() => remove(name)}
                aria-label={`Remove ${name}`}
                className="text-zinc-500 hover:text-red-600"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
