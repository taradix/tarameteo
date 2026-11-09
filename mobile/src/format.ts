import { useTranslation } from "react-i18next";

export function useFormat() {
  const { t, i18n } = useTranslation();
  const num = (v: number | null | undefined, digits: number) =>
    v == null ? "–" : v.toLocaleString(i18n.language, { minimumFractionDigits: digits, maximumFractionDigits: digits });
  // Times of day within a day, dates beyond.
  const tick = (ms: number, hours: number) =>
    hours <= 24
      ? new Date(ms).toLocaleTimeString(i18n.language, { hour: "2-digit", minute: "2-digit" })
      : new Date(ms).toLocaleDateString(i18n.language, { day: "numeric", month: "short" });
  const when = (ms: number) =>
    new Date(ms).toLocaleString(i18n.language, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  return { t, i18n, num, tick, when };
}
