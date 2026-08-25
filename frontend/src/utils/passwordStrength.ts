import type { ZxcvbnFactory, ZxcvbnResult } from "@zxcvbn-ts/core"

type PasswordAnalyzer = Pick<ZxcvbnFactory, "check">
type PasswordAnalyzerLoader = () => Promise<PasswordAnalyzer>

export function createPasswordStrengthAnalyzer(loadAnalyzer: PasswordAnalyzerLoader) {
  let analyzer: PasswordAnalyzer | undefined
  let analyzerPromise: Promise<PasswordAnalyzer> | undefined

  async function loadPasswordAnalyzer(): Promise<PasswordAnalyzer> {
    if (analyzer) return analyzer

    analyzerPromise ??= loadAnalyzer()
      .then((loadedAnalyzer) => {
        analyzer = loadedAnalyzer
        return loadedAnalyzer
      })
      .catch((error: unknown) => {
        analyzerPromise = undefined
        throw error
      })

    return analyzerPromise
  }

  return async (password: string): Promise<ZxcvbnResult> =>
    (await loadPasswordAnalyzer()).check(password)
}

export const analyzePasswordStrength = createPasswordStrengthAnalyzer(async () => {
  const [{ ZxcvbnFactory: Factory }, common] = await Promise.all([
    import("@zxcvbn-ts/core"),
    import("@zxcvbn-ts/language-common"),
  ])
  return new Factory({
    dictionary: common.dictionary,
    graphs: common.adjacencyGraphs,
  })
})
