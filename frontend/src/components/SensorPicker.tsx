import { useRef, useState, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";

interface Props {
  selected: string[];
  hidden: string[];
  available: string[];
  onChange: (sensors: string[]) => void;
  onHiddenChange: (hidden: string[]) => void;
}

export function SensorPicker({ selected, hidden, available, onChange, onHiddenChange }: Props) {
  const { t } = useTranslation();
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

  const remove = (name: string) => {
    onChange(selected.filter((s) => s !== name));
    onHiddenChange(hidden.filter((h) => h !== name));
  };

  const toggle = (name: string) =>
    onHiddenChange(hidden.includes(name) ? hidden.filter((h) => h !== name) : [...hidden, name]);

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") add();
  };

  const suggestions = focused ? available.filter((s) => !selected.includes(s)) : [];

  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <h2 className="mb-3 text-lg font-semibold">{t("sensors.title")}</h2>

      <div className="flex gap-2">
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          placeholder={t("sensors.placeholder")}
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
          {t("sensors.add")}
        </button>
      </div>

      {selected.length === 0 ? (
        <p className="mt-3 text-sm text-zinc-500">{t("sensors.none")}</p>
      ) : (
        <ul className="mt-3 flex flex-wrap gap-2">
          {selected.map((name) => {
            const isActive = !hidden.includes(name);
            return (
              <li key={name} className="flex items-center rounded-full text-sm overflow-hidden">
                <button
                  type="button"
                  onClick={() => toggle(name)}
                  aria-label={t("sensors.toggle", { name })}
                  aria-pressed={isActive}
                  className={`pl-3 pr-2 py-1 ${isActive ? "bg-blue-600 text-white" : "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400"}`}
                >
                  {name}
                </button>
                <button
                  type="button"
                  onClick={() => remove(name)}
                  aria-label={t("sensors.remove", { name })}
                  className={`px-2 py-1 ${isActive ? "bg-blue-600 text-blue-200 hover:text-white" : "bg-zinc-100 text-zinc-400 hover:text-red-600 dark:bg-zinc-800 dark:text-zinc-500"}`}
                >
                  ×
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
