export const SANITIZER_WASM_PATH: string
export const CRYPTO_WASM_PATH: string
export const DEFAULT_SEED: number
export const DEFAULT_ITERATIONS: number

export interface FuzzCampaignOptions {
  sanitizerPath?: string
  cryptoPath?: string
  seed?: number
  iterations?: number
}

export interface FuzzCampaignResult {
  ok: boolean
  executed: number
  failures: string[]
}

/** Why `filePath` is not a compiled WebAssembly module, or null when it is one. */
export function wasmArtifactProblem(filePath: string): string | null
/** Deterministic generator; the same seed always yields the same sequence. */
export function createRandom(seed: number): () => number
export function generateText(random: () => number): string
export function generateBytes(random: () => number, maxLength: number): Uint8Array
/** Describes the first unsafe construct left in sanitizer output, or null when it is clean. */
export function sanitizedMarkupViolation(output: unknown): string | null
export function runFuzzCampaign(options?: FuzzCampaignOptions): Promise<FuzzCampaignResult>
