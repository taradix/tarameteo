import { type FormEvent, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import type { AlertCreate } from "../types";

type AlertField = AlertCreate["field"];

const ALERT_FIELDS: AlertField[] = ["temperature", "humidity", "pressure", "rain", "snow", "offline"];
const CONDITIONS = ["below", "above"] as const;

// Emails come in the language of the page they were asked from.
const emailLanguage = (language?: string) => (language === "fr" ? "fr" : "en");

// One header button for every screen size; on phones the dialog is a bottom
// sheet so the form isn't buried under the charts.
export function AlertsDialog({ sensors }: { sensors: string[] }) {
  const { t } = useTranslation();
  const ref = useRef<HTMLDialogElement>(null);
  const [view, setView] = useState<"create" | "manage" | null>(null);

  const open = () => { setView("create"); ref.current?.showModal(); };
  const close = () => ref.current?.close();

  return (
    <>
      <button
        type="button"
        onClick={open}
        className="rounded border border-zinc-300 px-3 py-1 text-sm hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-900"
      >
        🔔 {t("alerts.create")}
      </button>
      <dialog
        ref={ref}
        onClose={() => setView(null)}
        // Clicks on the backdrop land on the dialog itself; the content is wrapped.
        onClick={(e) => e.target === e.currentTarget && close()}
        className="mb-0 mt-auto w-full max-w-none rounded-t-lg bg-white text-zinc-900 backdrop:bg-black/40 sm:m-auto sm:max-w-md sm:rounded-lg dark:bg-zinc-950 dark:text-zinc-100"
      >
        <div className="space-y-4 p-4">
          {view === "create" && (
            <>
              {sensors.length > 0
                ? <AlertForm sensors={sensors} onClose={close} />
                : <p className="text-sm text-zinc-500">{t("alerts.noSensors")}</p>}
              <button
                type="button"
                onClick={() => setView("manage")}
                className="text-sm text-blue-600 hover:text-blue-800 underline"
              >
                {t("alerts.manage")}
              </button>
            </>
          )}
          {view === "manage" && <ManageAlerts onClose={close} />}
        </div>
      </dialog>
    </>
  );
}

function AlertForm({ sensors, onClose }: { sensors: string[]; onClose: () => void }) {
  const { t, i18n } = useTranslation();
  const [sensor, setSensor] = useState(sensors[0] ?? "");
  const [field, setField] = useState<AlertField>("temperature");
  const [condition, setCondition] = useState<"above" | "below">("below");
  const [threshold, setThreshold] = useState("");
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");
  // Offline: "no reading for more than N hours".
  const offline = field === "offline";

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setStatus("sending");
    try {
      await api.createAlert({
        email,
        sensor,
        field,
        condition: offline ? "above" : condition,
        threshold: Number(threshold),
        language: emailLanguage(i18n.resolvedLanguage),
      });
      setStatus("sent");
    } catch {
      setStatus("error");
    }
  };

  if (status === "sent") {
    return (
      <div className="rounded border border-green-300 bg-green-50 p-3 text-sm text-green-800">
        {t("alerts.confirmationSent")}
        <button type="button" onClick={onClose} className="ml-2 underline">
          {t("alerts.close")}
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3 text-sm">
      <h3 className="font-semibold">{t("alerts.title")}</h3>

      <div className="flex flex-wrap gap-2">
        <select value={sensor} onChange={(e) => setSensor(e.target.value)} className="border rounded px-2 py-1">
          {sensors.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>

        <select value={field} onChange={(e) => setField(e.target.value as AlertField)} className="border rounded px-2 py-1">
          {ALERT_FIELDS.map((f) => <option key={f} value={f}>{t(`alerts.fields.${f}`)}</option>)}
        </select>

        {!offline && (
          <select value={condition} onChange={(e) => setCondition(e.target.value as "above" | "below")} className="border rounded px-2 py-1">
            {CONDITIONS.map((c) => <option key={c} value={c}>{t(`alerts.conditions.${c}`)}</option>)}
          </select>
        )}

        <input
          type="number"
          step="any"
          min={offline ? 1 : undefined}
          max={offline ? 720 : undefined}
          value={threshold}
          onChange={(e) => setThreshold(e.target.value)}
          placeholder={offline ? t("alerts.hours") : t("alerts.threshold")}
          aria-label={offline ? t("alerts.hours") : t("alerts.threshold")}
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
          onClick={onClose}
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

// No accounts: the link to see and stop your alerts comes by email.
function ManageAlerts({ onClose }: { onClose: () => void }) {
  const { t, i18n } = useTranslation();
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setStatus("sending");
    try {
      await api.manageAlerts({ email, language: emailLanguage(i18n.resolvedLanguage) });
      setStatus("sent");
    } catch {
      setStatus("error");
    }
  };

  if (status === "sent") {
    return (
      <div className="rounded border border-green-300 bg-green-50 p-3 text-sm text-green-800">
        {t("alerts.manageSent")}
        <button type="button" onClick={onClose} className="ml-2 underline">
          {t("alerts.close")}
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3 text-sm">
      <h3 className="font-semibold">{t("alerts.manage")}</h3>
      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder={t("alerts.email")}
        aria-label={t("alerts.email")}
        required
        className="border rounded px-2 py-1 w-full"
      />
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={status === "sending"}
          className="bg-blue-600 text-white rounded px-3 py-1 hover:bg-blue-700 disabled:opacity-50"
        >
          {status === "sending" ? t("alerts.sending") : t("alerts.manageSubmit")}
        </button>
        <button type="button" onClick={onClose} className="text-zinc-500 hover:text-zinc-700 underline">
          {t("alerts.cancel")}
        </button>
      </div>
      {status === "error" && <p className="text-red-600">{t("alerts.manageError")}</p>}
    </form>
  );
}
