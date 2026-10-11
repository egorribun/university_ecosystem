import * as v from "valibot"

/** Non-secret origin-wide generation. It never bootstraps an identity: a live
 * server-issued in-memory key must independently match before private cache use. */
const GENERATION_KEY = "ecosystem.session.generation.v1"
const Generation = v.object({
  nonce: v.pipe(v.string(), v.minLength(1), v.maxLength(128)),
  hash: v.nullable(v.pipe(v.string(), v.minLength(1), v.maxLength(128))),
})
let epoch = 0
// A failed localStorage write must not erase an already observed cross-tab mismatch.
let failedRotationGeneration: string | null | undefined
let failedRotationWasStale = false
const readGeneration = () => {
  try {
    const raw = globalThis.localStorage?.getItem(GENERATION_KEY)
    if (!raw) return null
    const parsed = v.safeParse(Generation, JSON.parse(raw))
    return parsed.success ? parsed.output : null
  } catch {
    return null
  }
}
export const getBrowserSessionGeneration = () => readGeneration()?.nonce ?? null
let boundGeneration = getBrowserSessionGeneration()
export const isCurrentBrowserSession = () => boundGeneration === getBrowserSessionGeneration()
const isStaleBrowserSessionBindingAt = (currentGeneration: string | null) => {
  if (failedRotationGeneration !== undefined) {
    if (failedRotationWasStale) return true
    return currentGeneration !== null && currentGeneration !== failedRotationGeneration
  }
  if (currentGeneration === null) return false
  return currentGeneration !== boundGeneration
}
export const hasStaleBrowserSessionBinding = () =>
  isStaleBrowserSessionBindingAt(getBrowserSessionGeneration())
export const hasFailedBrowserSessionRotation = () => failedRotationGeneration !== undefined
export const acceptBrowserSessionGeneration = () => {
  boundGeneration = getBrowserSessionGeneration()
  failedRotationGeneration = undefined
  failedRotationWasStale = false
}
export const matchesBrowserSession = (hash: string, nonce: string) => {
  const current = readGeneration()
  return current?.hash === hash && current.nonce === nonce
}
export const getSessionEpoch = () => epoch
export const invalidateSessionEpoch = () => {
  epoch += 1
}
export const rotateBrowserSession = () => {
  const generationBeforeRotation = getBrowserSessionGeneration()
  const wasStaleBeforeRotation = isStaleBrowserSessionBindingAt(generationBeforeRotation)
  invalidateSessionEpoch()
  try {
    const nonce = crypto.randomUUID()
    globalThis.localStorage?.setItem(GENERATION_KEY, JSON.stringify({ nonce, hash: null }))
    boundGeneration = getBrowserSessionGeneration()
    failedRotationGeneration = undefined
    failedRotationWasStale = false
  } catch {
    boundGeneration = null /* live network auth remains usable; no offline handshake */
    failedRotationGeneration = generationBeforeRotation
    failedRotationWasStale = wasStaleBeforeRotation
  }
}
export const establishBrowserSession = (
  hash: string,
  expectedGeneration: string | null
): string | null => {
  try {
    const current = readGeneration()
    if ((current?.nonce ?? null) !== expectedGeneration) return null
    const nonce =
      current?.hash === hash || current?.hash === null ? current.nonce : crypto.randomUUID()
    globalThis.localStorage.setItem(GENERATION_KEY, JSON.stringify({ nonce, hash }))
    boundGeneration = nonce
    failedRotationGeneration = undefined
    failedRotationWasStale = false
    return nonce
  } catch {
    return null
  }
}
export const captureSessionEpoch = (expected = epoch) => {
  const captured = epoch
  const generation = getBrowserSessionGeneration()
  return () =>
    expected === captured &&
    captured === epoch &&
    generation === getBrowserSessionGeneration() &&
    isCurrentBrowserSession()
}
