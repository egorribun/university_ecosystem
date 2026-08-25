import type { ZxcvbnFactory, ZxcvbnResult } from "@zxcvbn-ts/core"

let analyzer: ZxcvbnFactory | undefined
let analyzerPromise: Promise<ZxcvbnFactory> | undefined

async function loadPasswordAnalyzer(): Promise<ZxcvbnFactory> {
  if (analyzer) return analyzer

  analyzerPromise ??= Promise.all([import("@zxcvbn-ts/core"), import("@zxcvbn-ts/language-common")])
    .then(([{ ZxcvbnFactory: Factory }, common]) => {
      analyzer = new Factory({
        dictionary: common.dictionary,
        graphs: common.adjacencyGraphs,
      })
      return analyzer
    })
    .catch((error: unknown) => {
      analyzerPromise = undefined
      throw error
    })

  return analyzerPromise
}

export async function analyzePasswordStrength(password: string): Promise<ZxcvbnResult> {
  return (await loadPasswordAnalyzer()).check(password)
}
