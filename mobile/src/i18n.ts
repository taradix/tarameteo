import { getLocales } from "expo-localization";
import { default as i18n } from "i18next";
import { initReactI18next } from "react-i18next";

import en from "./locales/en.json";
import fr from "./locales/fr.json";

// Copied from frontend/src/locales; follows the device language, no in-app toggle.
void i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    fr: { translation: fr },
  },
  lng: getLocales()[0]?.languageCode ?? "en",
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});
