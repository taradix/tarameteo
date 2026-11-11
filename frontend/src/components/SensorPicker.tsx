import { useId, useRef, useState, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { useSensorSearch } from "../hooks/useSensors";

// A list past this is a scroll, not a suggestion.
const SUGGESTIONS = 20;

interface Props {
  selected: string[];
  hidden: string[];
  onChange: (sensors: string[]) => void;
  onHiddenChange: (hidden: string[]) => void;
}

export function SensorPicker({ selected, hidden, onChange, onHiddenChange }: Props) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const [input, setInput] = useState("");
  const [open, setOpen] = useState(false);
  // Highlighted suggestion, -1 for none; focus stays on the input either way.
  const [active, setActive] = useState(-1);
  const listId = useId();
  const search = useSensorSearch(input, SUGGESTIONS);

  const add = (name = input.trim()) => {
    if (!name || selected.includes(name)) return;
    onChange([...selected, name]);
    setInput("");
    setActive(-1);
    inputRef.current?.blur();
  };

  const remove = (name: string) => {
    onChange(selected.filter((s) => s !== name));
    onHiddenChange(hidden.filter((h) => h !== name));
  };

  const toggle = (name: string) =>
    onHiddenChange(hidden.includes(name) ? hidden.filter((h) => h !== name) : [...hidden, name]);

  // A sensor with both kinds comes back twice; one suggestion is enough.
  const names = new Set(search.data?.sensors.map((s) => s.name));
  const suggestions = open && input.trim() ? [...names].filter((s) => !selected.includes(s)) : [];
  // Late results can shrink the list under the highlight.
  const highlighted = active < suggestions.length ? active : -1;

  // The combobox keys from the WAI-ARIA authoring practices.
  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setOpen(true);
      const step = e.key === "ArrowDown" ? 1 : -1;
      setActive(Math.min(Math.max(highlighted + step, -1), suggestions.length - 1));
    } else if (e.key === "Enter") {
      add(suggestions[highlighted]);
    } else if (e.key === "Escape") {
      setOpen(false);
      setActive(-1);
    }
  };

  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <h2 className="mb-3 text-lg font-semibold">{t("sensors.title")}</h2>

      <div className="relative flex gap-2">
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => {
            setInput(e.target.value);
            setOpen(true);
            setActive(-1);
          }}
          onKeyDown={onKeyDown}
          onFocus={() => setOpen(true)}
          onBlur={() => setOpen(false)}
          placeholder={t("sensors.placeholder")}
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={suggestions.length > 0}
          aria-controls={listId}
          aria-activedescendant={highlighted >= 0 ? `${listId}-${highlighted}` : undefined}
          className="flex-1 rounded border border-zinc-300 bg-white px-2 py-1 dark:border-zinc-700 dark:bg-zinc-900"
        />
        {/* Not a <datalist>: Firefox on Android never shows one. */}
        {suggestions.length > 0 && (
          <ul
            id={listId}
            role="listbox"
            className="absolute left-0 right-0 top-full z-10 mt-1 max-h-60 overflow-y-auto rounded border border-zinc-300 bg-white shadow dark:border-zinc-700 dark:bg-zinc-900"
          >
            {suggestions.map((s, i) => (
              <li
                key={s}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={i === highlighted}
                ref={i === highlighted ? (el) => el?.scrollIntoView({ block: "nearest" }) : undefined}
                // Keep focus on the input, or its blur hides this list before the click lands.
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => add(s)}
                className={`cursor-pointer px-2 py-2 hover:bg-zinc-100 dark:hover:bg-zinc-800 ${i === highlighted ? "bg-zinc-100 dark:bg-zinc-800" : ""}`}
              >
                {s}
              </li>
            ))}
          </ul>
        )}
        <button
          type="button"
          onClick={() => add()}
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
