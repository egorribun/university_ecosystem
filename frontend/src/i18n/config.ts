import i18n, {
  createInstance,
  type InitOptions,
  type Resource,
  type ResourceKey,
  type i18n as I18nInstance,
} from "i18next"
import { initReactI18next } from "react-i18next"
import { defaultNS, fallbackLng, localeMeta, namespaces, supportedLngs } from "./metadata"

// Keep the locale graph explicit. Besides making the bundled resource
// denominator deterministic, static JSON imports are understood by both Vite
// and the mutation-test parser (unlike an instrumented import.meta.glob call).
import enActivity from "./locales/en/activity.json"
import enAdmin from "./locales/en/admin.json"
import enAuth from "./locales/en/auth.json"
import enCommon from "./locales/en/common.json"
import enDashboard from "./locales/en/dashboard.json"
import enEvents from "./locales/en/events.json"
import enMap from "./locales/en/map.json"
import enMessenger from "./locales/en/messenger.json"
import enNavigation from "./locales/en/navigation.json"
import enNews from "./locales/en/news.json"
import enNotifications from "./locales/en/notifications.json"
import enProfile from "./locales/en/profile.json"
import enSchedule from "./locales/en/schedule.json"
import enSettings from "./locales/en/settings.json"
import enStories from "./locales/en/stories.json"
import enSystem from "./locales/en/system.json"
import ruActivity from "./locales/ru/activity.json"
import ruAdmin from "./locales/ru/admin.json"
import ruAuth from "./locales/ru/auth.json"
import ruCommon from "./locales/ru/common.json"
import ruDashboard from "./locales/ru/dashboard.json"
import ruEvents from "./locales/ru/events.json"
import ruMap from "./locales/ru/map.json"
import ruMessenger from "./locales/ru/messenger.json"
import ruNavigation from "./locales/ru/navigation.json"
import ruNews from "./locales/ru/news.json"
import ruNotifications from "./locales/ru/notifications.json"
import ruProfile from "./locales/ru/profile.json"
import ruSchedule from "./locales/ru/schedule.json"
import ruSettings from "./locales/ru/settings.json"
import ruStories from "./locales/ru/stories.json"
import ruSystem from "./locales/ru/system.json"

declare global {
  var __ssrI18nGetter__: (() => I18nInstance | undefined) | undefined
}

export const localeModules: Record<string, ResourceKey> = {
  "./locales/en/activity.json": enActivity,
  "./locales/en/admin.json": enAdmin,
  "./locales/en/auth.json": enAuth,
  "./locales/en/common.json": enCommon,
  "./locales/en/dashboard.json": enDashboard,
  "./locales/en/events.json": enEvents,
  "./locales/en/map.json": enMap,
  "./locales/en/messenger.json": enMessenger,
  "./locales/en/navigation.json": enNavigation,
  "./locales/en/news.json": enNews,
  "./locales/en/notifications.json": enNotifications,
  "./locales/en/profile.json": enProfile,
  "./locales/en/schedule.json": enSchedule,
  "./locales/en/settings.json": enSettings,
  "./locales/en/stories.json": enStories,
  "./locales/en/system.json": enSystem,
  "./locales/ru/activity.json": ruActivity,
  "./locales/ru/admin.json": ruAdmin,
  "./locales/ru/auth.json": ruAuth,
  "./locales/ru/common.json": ruCommon,
  "./locales/ru/dashboard.json": ruDashboard,
  "./locales/ru/events.json": ruEvents,
  "./locales/ru/map.json": ruMap,
  "./locales/ru/messenger.json": ruMessenger,
  "./locales/ru/navigation.json": ruNavigation,
  "./locales/ru/news.json": ruNews,
  "./locales/ru/notifications.json": ruNotifications,
  "./locales/ru/profile.json": ruProfile,
  "./locales/ru/schedule.json": ruSchedule,
  "./locales/ru/settings.json": ruSettings,
  "./locales/ru/stories.json": ruStories,
  "./locales/ru/system.json": ruSystem,
}

/** Build the i18next resource tree from Vite's eagerly imported locale modules. */
export const buildResources = (modules: Record<string, ResourceKey>): Resource =>
  Object.entries(modules).reduce<Resource>((result, [path, resource]) => {
    const match = /^\.\/locales\/([^/]*)\/([^/]*)\.json$/.exec(path)
    if (!match) return result

    const language = match[1]
    const namespace = match[2]
    if (!language || !namespace) return result
    result[language] ??= {}
    result[language][namespace] = resource
    return result
  }, {})

export const resources: Resource = buildResources(localeModules)

const createOptions = (language: string): InitOptions => ({
  defaultNS,
  fallbackLng,
  supportedLngs,
  ns: namespaces,
  resources,
  lng: language,
  load: "currentOnly",
  nonExplicitSupportedLngs: false,
  interpolation: {
    escapeValue: false,
  },
  react: {
    useSuspense: false,
  },
  returnNull: false,
  saveMissing: false,
  cleanCode: true,
  partialBundledLanguages: false,
  pluralSeparator: "_",
  keySeparator: ".",
  // All locale resources are bundled. Synchronous initialization guarantees
  // the first server and browser render see the same translated text.
  initAsync: false,
})

const configureInstance = (instance: I18nInstance, language: string): I18nInstance => {
  void instance.use(initReactI18next).init(createOptions(language))
  return instance
}

export const createI18nInstance = (language = fallbackLng): I18nInstance =>
  configureInstance(createInstance(), language)

export const resolveBootstrapLanguage = (): string => {
  if (typeof window === "undefined") return fallbackLng
  const selected = window.__UE_SELECTED_LANG__
  return supportedLngs.includes(selected as (typeof supportedLngs)[number])
    ? selected!
    : fallbackLng
}

configureInstance(i18n, resolveBootstrapLanguage())

export { defaultNS, fallbackLng, supportedLngs, namespaces, localeMeta }

export default i18n
