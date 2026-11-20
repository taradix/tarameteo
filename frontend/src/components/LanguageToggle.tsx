import { useTranslation } from "react-i18next";

export function LanguageToggle() {
  const { t, i18n } = useTranslation();
  // resolvedLanguage maps a detected locale like "en-US" to a supported one ("en").
  const other = i18n.resolvedLanguage === "en" ? "fr" : "en";

  return (
    <button
      type="button"
      onClick={() => i18n.changeLanguage(other)}
      // language.toggle is worded in the language it switches to, for those who can't read this one.
      lang={other}
      aria-label={t("language.toggle")}
      className="rounded border border-zinc-300 px-3 py-1 text-sm hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-900"
    >
      {other.toUpperCase()}
    </button>
  );
}
