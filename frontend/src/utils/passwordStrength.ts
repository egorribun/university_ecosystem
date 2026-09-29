import type { ZxcvbnFactory, ZxcvbnResult } from "@zxcvbn-ts/core"

type PasswordAnalyzer = Pick<ZxcvbnFactory, "check">
export type StrengthLocale = "en" | "ru"
type PasswordAnalyzerLoader = (locale: StrengthLocale) => Promise<PasswordAnalyzer>

export function normalizePasswordStrengthLocale(language?: string): StrengthLocale {
  return language?.toLowerCase().startsWith("en") ? "en" : "ru"
}

export function createPasswordStrengthAnalyzer(loadAnalyzer: PasswordAnalyzerLoader) {
  // One cached promise per locale; a failed load is forgotten so the next
  // check retries it.
  const analyzerPromises = new Map<StrengthLocale, Promise<PasswordAnalyzer>>()

  function loadPasswordAnalyzer(locale: StrengthLocale): Promise<PasswordAnalyzer> {
    let analyzerPromise = analyzerPromises.get(locale)
    if (!analyzerPromise) {
      analyzerPromise = loadAnalyzer(locale).catch((error: unknown) => {
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
