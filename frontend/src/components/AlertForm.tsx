import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type AlertCreateRequest } from "../api";
import type { WeatherField } from "../types";

const ALERT_FIELDS: WeatherField[] = ["temperature", "humidity", "pressure", "rain", "snow"];
const CONDITIONS = ["below", "above"] as const;

interface AlertFormProps {
  sensors: string[];
}

export function AlertForm({ sensors }: AlertFormProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [sensor, setSensor] = useState(sensors[0] ?? "");
  const [field, setField] = useState<WeatherField>("temperature");
  const [condition, setCondition] = useState<"above" | "below">("below");
  const [threshold, setThreshold] = useState("");
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setStatus("sending");
    try {
      const request: AlertCreateRequest = {
        email,
        sensor,
        field,
        condition,
        threshold: Number(threshold),
      };
      await api.createAlert(request);
      setStatus("sent");
    } catch {
      setStatus("error");
    }
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="text-sm text-blue-600 hover:text-blue-800 underline"
      >
        🔔 {t("alerts.create")}
      </button>
    );
  }

  if (status === "sent") {
    return (
      <div className="rounded border border-green-300 bg-green-50 p-3 text-sm text-green-800">
        {t("alerts.confirmationSent")}
        <button
          type="button"
          onClick={() => { setStatus("idle"); setOpen(false); }}
          className="ml-2 underline"
        >
          {t("alerts.close")}
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="rounded border border-zinc-200 p-4 space-y-3 text-sm">
      <h3 className="font-semibold">{t("alerts.title")}</h3>

      <div className="flex flex-wrap gap-2">
        <select value={sensor} onChange={(e) => setSensor(e.target.value)} className="border rounded px-2 py-1">
          {sensors.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>

        <select value={field} onChange={(e) => setField(e.target.value as WeatherField)} className="border rounded px-2 py-1">
          {ALERT_FIELDS.map((f) => <option key={f} value={f}>{t(`alerts.fields.${f}`)}</option>)}
        </select>

        <select value={condition} onChange={(e) => setCondition(e.target.value as "above" | "below")} className="border rounded px-2 py-1">
          {CONDITIONS.map((c) => <option key={c} value={c}>{t(`alerts.conditions.${c}`)}</option>)}
        </select>

        <input
          type="number"
          step="any"
          value={threshold}
          onChange={(e) => setThreshold(e.target.value)}
          placeholder={t("alerts.threshold")}
          required
          className="border rounded px-2 py-1 w-24"
        />
      </div>

      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder={t("alerts.email")}
        required
        className="border rounded px-2 py-1 w-full"
      />

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={status === "sending"}
          className="bg-blue-600 text-white rounded px-3 py-1 hover:bg-blue-700 disabled:opacity-50"
        >
          {status === "sending" ? t("alerts.sending") : t("alerts.submit")}
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-zinc-500 hover:text-zinc-700 underline"
        >
          {t("alerts.cancel")}
        </button>
      </div>

      {status === "error" && (
        <p className="text-red-600">{t("alerts.error")}</p>
      )}
    </form>
  );
}
