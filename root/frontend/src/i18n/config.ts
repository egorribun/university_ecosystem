import i18n from "i18next"
import { initReactI18next } from "react-i18next"

import commonEn from "./locales/en/common.json" assert { type: "json" }
import commonRu from "./locales/ru/common.json" assert { type: "json" }
import navigationEn from "./locales/en/navigation.json" assert { type: "json" }
import navigationRu from "./locales/ru/navigation.json" assert { type: "json" }
import dashboardEn from "./locales/en/dashboard.json" assert { type: "json" }
import dashboardRu from "./locales/ru/dashboard.json" assert { type: "json" }
import authEn from "./locales/en/auth.json" assert { type: "json" }
import authRu from "./locales/ru/auth.json" assert { type: "json" }
import settingsEn from "./locales/en/settings.json" assert { type: "json" }
import settingsRu from "./locales/ru/settings.json" assert { type: "json" }
import systemEn from "./locales/en/system.json" assert { type: "json" }
import systemRu from "./locales/ru/system.json" assert { type: "json" }

export const defaultNS = "common"

export const resources = {
  en: {
    common: commonEn,
    navigation: navigationEn,
    dashboard: dashboardEn,
    auth: authEn,
    settings: settingsEn,
    system: systemEn,
  },
  ru: {
    common: commonRu,
    navigation: navigationRu,
    dashboard: dashboardRu,
    auth: authRu,
    settings: settingsRu,
    system: systemRu,
  },
} as const

const fallbackLng = "ru"

void i18n
  .use(initReactI18next)
  .init({
    resources,
    defaultNS,
    fallbackLng,
    supportedLngs: ["en", "ru"],
    lng: fallbackLng,
    interpolation: {
      escapeValue: false,
    },
    react: {
      useSuspense: false,
    },
    returnNull: false,
  })

export default i18n
