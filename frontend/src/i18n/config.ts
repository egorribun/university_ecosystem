import i18n, { type ResourceKey } from "i18next"
import { initReactI18next } from "react-i18next"
import type { BackendModule } from "i18next"
import { defaultNS, fallbackLng, localeMeta, namespaces, supportedLngs } from "./metadata"

export const localeLoaders = import.meta.glob("./locales/*/*.json", {
  import: "default",
})

export const dynamicBackend: BackendModule = {
  type: "backend",
  init() {
    // No initialization required for the dynamic import backend
  },
  read(language, namespace, callback) {
    const key = `./locales/${language}/${namespace}.json`
    const loader = localeLoaders[key]
    if (!loader) {
      callback(new Error(`Missing locale file for ${language}/${namespace}`), null)
      return
    }

    ;(loader as () => Promise<unknown>)()
      .then((module) =>
        callback(
          null,
          ((module as { default?: ResourceKey }).default ?? (module as ResourceKey)) as ResourceKey
        )
      )
      .catch((error) => callback(error as Error, null))
  },
}

void i18n
  .use(dynamicBackend)
  .use(initReactI18next)
  .init({
    defaultNS,
    fallbackLng,
    supportedLngs,
    ns: namespaces,
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
    partialBundledLanguages: true,
    pluralSeparator: "_",
    keySeparator: ".",
  })

export { defaultNS, fallbackLng, supportedLngs, namespaces, localeMeta }

export default i18n
