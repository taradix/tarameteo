import { format, parseISO } from "date-fns";

interface Props {
  start: Date;
  end: Date;
  onChange: (range: { start?: Date; end?: Date }) => void;
}

const LOCAL_FORMAT = "yyyy-MM-dd'T'HH:mm";

export function DateRangePicker({ start, end, onChange }: Props) {
  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <h2 className="mb-3 text-lg font-semibold">Date range</h2>
      <div className="flex flex-wrap gap-3">
        <label className="flex flex-col text-sm">
          <span className="mb-1">Start</span>
          <input
            type="datetime-local"
            value={format(start, LOCAL_FORMAT)}
            onChange={(e) => onChange({ start: parseISO(e.target.value) })}
            className="rounded border border-zinc-300 bg-white px-2 py-1 dark:border-zinc-700 dark:bg-zinc-900"
          />
        </label>
        <label className="flex flex-col text-sm">
          <span className="mb-1">End</span>
          <input
            type="datetime-local"
            value={format(end, LOCAL_FORMAT)}
            onChange={(e) => onChange({ end: parseISO(e.target.value) })}
            className="rounded border border-zinc-300 bg-white px-2 py-1 dark:border-zinc-700 dark:bg-zinc-900"
          />
        </label>
      </div>
    </section>
  );
}
