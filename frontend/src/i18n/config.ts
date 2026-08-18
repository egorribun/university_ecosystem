import i18n, {
  createInstance,
  type InitOptions,
  type Resource,
  type ResourceKey,
  type i18n as I18nInstance,
} from "i18next"
import { initReactI18next } from "react-i18next"
import { defaultNS, fallbackLng, localeMeta, namespaces, supportedLngs } from "./metadata"

declare global {
  var __ssrI18nGetter__: (() => I18nInstance | undefined) | undefined
}

export const localeModules = import.meta.glob<ResourceKey>("./locales/*/*.json", {
  eager: true,
  import: "default",
})

export const resources: Resource = Object.entries(localeModules).reduce<Resource>(
  (result, [path, resource]) => {
    const match = /^\.\/locales\/([^/]+)\/([^/]+)\.json$/.exec(path)
    if (!match) return result

    const language = match[1]
    const namespace = match[2]
    if (!language || !namespace) return result
    result[language] ??= {}
    result[language][namespace] = resource
    return result
  },
  {}
)

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
  initImmediate: false,
})

const configureInstance = (instance: I18nInstance, language: string): I18nInstance => {
  void instance.use(initReactI18next).init(createOptions(language))
  return instance
}

export const createI18nInstance = (language = fallbackLng): I18nInstance =>
  configureInstance(createInstance(), language)

const resolveBootstrapLanguage = (): string => {
  if (typeof window === "undefined") return fallbackLng
  const selected = window.__UE_SELECTED_LANG__
  return supportedLngs.includes(selected as (typeof supportedLngs)[number])
    ? selected!
    : fallbackLng
}

configureInstance(i18n, resolveBootstrapLanguage())

export { defaultNS, fallbackLng, supportedLngs, namespaces, localeMeta }

export default i18n
