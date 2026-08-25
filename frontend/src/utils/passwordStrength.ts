import type { ZxcvbnFactory, ZxcvbnResult } from "@zxcvbn-ts/core"

type PasswordAnalyzer = Pick<ZxcvbnFactory, "check">
export type PasswordStrengthLocale = "en" | "ru"
type PasswordAnalyzerLoader = (locale: PasswordStrengthLocale) => Promise<PasswordAnalyzer>

export function normalizePasswordStrengthLocale(language?: string): PasswordStrengthLocale {
  return language?.toLowerCase().startsWith("en") ? "en" : "ru"
}

export function createPasswordStrengthAnalyzer(loadAnalyzer: PasswordAnalyzerLoader) {
  const analyzers = new Map<PasswordStrengthLocale, PasswordAnalyzer>()
  const analyzerPromises = new Map<PasswordStrengthLocale, Promise<PasswordAnalyzer>>()

  async function loadPasswordAnalyzer(locale: PasswordStrengthLocale): Promise<PasswordAnalyzer> {
    const analyzer = analyzers.get(locale)
    if (analyzer) return analyzer

    let analyzerPromise = analyzerPromises.get(locale)
    if (!analyzerPromise) {
      analyzerPromise = loadAnalyzer(locale)
        .then((loadedAnalyzer) => {
          analyzers.set(locale, loadedAnalyzer)
          return loadedAnalyzer
        })
        .catch((error: unknown) => {
          analyzerPromises.delete(locale)
          throw error
        })
      analyzerPromises.set(locale, analyzerPromise)
    }

    return analyzerPromise
  }

  return async (password: string, language?: string): Promise<ZxcvbnResult> => {
    const locale = normalizePasswordStrengthLocale(language)
    return (await loadPasswordAnalyzer(locale)).check(password)
  }
}

export const analyzePasswordStrength = createPasswordStrengthAnalyzer(async (locale) => {
  const [{ ZxcvbnFactory: Factory }, common, language] = await Promise.all([
    import("@zxcvbn-ts/core"),
    import("@zxcvbn-ts/language-common"),
    locale === "en" ? import("@zxcvbn-ts/language-en") : import("@zxcvbn-ts/language-ru"),
  ])
  return new Factory({
    dictionary: {
      ...common.dictionary,
      ...language.dictionary,
    },
    graphs: common.adjacencyGraphs,
    translations: language.translations,
  })
})
