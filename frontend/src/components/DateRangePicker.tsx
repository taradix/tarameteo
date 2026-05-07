import { useState } from "react";
import { useTranslation } from "react-i18next";
import { format, parseISO } from "date-fns";

interface Props {
  preset: string;
  start: Date;
  end: Date | null;
  onChange: (params: { preset?: string | null; start?: Date | null; end?: Date | null }) => void;
}

const PRESET_KEYS = ["live", "yesterday", "7d", "30d"] as const;
type PresetKey = (typeof PRESET_KEYS)[number];

const LOCAL_FORMAT = "yyyy-MM-dd'T'HH:mm";

export function RangePicker({ preset, start, end, onChange }: Props) {
  const { t } = useTranslation();
  const [customExpanded, setCustomExpanded] = useState(false);

  const PRESETS: { key: PresetKey; label: string }[] = [
    { key: "live",      label: t("dateRange.live")      },
    { key: "yesterday", label: t("dateRange.yesterday") },
    { key: "7d",        label: t("dateRange.last7d")    },
    { key: "30d",       label: t("dateRange.last30d")   },
  ];

  const isKnownPreset = PRESET_KEYS.some((k) => k === preset);
  const isCustom = !isKnownPreset;
  const showCustom = isCustom || customExpanded;

  const btnClass = (active: boolean) =>
    `rounded px-3 py-1 text-sm ${
      active
        ? "bg-blue-600 text-white"
        : "border border-zinc-300 bg-white text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800"
    }`;

  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <h2 className="mb-3 text-lg font-semibold">{t("dateRange.title")}</h2>
      <div className="flex flex-wrap gap-2">
        {PRESETS.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            onClick={() => { onChange({ preset: key, start: null, end: null }); setCustomExpanded(false); }}
            className={btnClass(preset === key)}
          >
            {label}
          </button>
        ))}
        <button
          type="button"
          onClick={() => { if (!isCustom) onChange({ preset: "custom", start, end }); setCustomExpanded((v) => !v); }}
          className={btnClass(showCustom)}
        >
          {t("dateRange.custom")}
        </button>
      </div>

      {showCustom && (
        <div className="mt-3 flex flex-wrap gap-3">
          <label className="flex flex-col text-sm">
            <span className="mb-1">{t("dateRange.start")}</span>
            <input
              type="datetime-local"
              value={format(start, LOCAL_FORMAT)}
              onChange={(e) => onChange({ preset: "custom", start: parseISO(e.target.value) })}
              className="rounded border border-zinc-300 bg-white px-2 py-1 dark:border-zinc-700 dark:bg-zinc-900"
            />
          </label>
          <label className="flex flex-col text-sm">
            <span className="mb-1">{t("dateRange.end")} <span className="text-zinc-400">({t("dateRange.endHint")})</span></span>
            <input
              type="datetime-local"
              value={end ? format(end, LOCAL_FORMAT) : ""}
              onChange={(e) => onChange({ preset: "custom", end: e.target.value ? parseISO(e.target.value) : null })}
              className="rounded border border-zinc-300 bg-white px-2 py-1 dark:border-zinc-700 dark:bg-zinc-900"
            />
          </label>
        </div>
      )}
    </section>
  );
}
