import * as v from "valibot"

/** Non-secret origin-wide generation. It never bootstraps an identity: a live
 * server-issued in-memory key must independently match before private cache use. */
const GENERATION_KEY = "ecosystem.session.generation.v1"
const Generation = v.object({
  nonce: v.pipe(v.string(), v.minLength(1), v.maxLength(128)),
  hash: v.nullable(v.pipe(v.string(), v.minLength(1), v.maxLength(128))),
})
type GenerationValue = v.InferOutput<typeof Generation>
type GenerationSnapshot =
  | { status: "present"; value: GenerationValue }
  | { status: "absent" }
  | { status: "invalid" }
  | { status: "unavailable" }

export type BrowserSessionTransitionOperation = "login" | "logout" | "unauthenticated-mfa"
export type BrowserSessionTransitionStatus = "verified" | "online-only" | "denied"
export type BrowserSessionTransition = {
  status: BrowserSessionTransitionStatus
  isCurrent: () => boolean
}

let epoch = 0
let latestTransitionAttempt = 0
// A failed localStorage write must not erase an already observed cross-tab mismatch.
let failedRotationGeneration: string | null | undefined
let failedRotationWasStale = false
let failedRotationSnapshot: GenerationSnapshot | undefined

const readGenerationSnapshot = (): GenerationSnapshot => {
  try {
    const storage = globalThis.localStorage
    if (!storage) return { status: "unavailable" }
    const raw = storage.getItem(GENERATION_KEY)
    if (raw === null) return { status: "absent" }
    let decoded: unknown
    try {
      decoded = JSON.parse(raw)
    } catch {
      return { status: "invalid" }
    }
    const parsed = v.safeParse(Generation, decoded)
    return parsed.success ? { status: "present", value: parsed.output } : { status: "invalid" }
  } catch {
    return { status: "unavailable" }
  }
}

const readGeneration = () => {
  const snapshot = readGenerationSnapshot()
  return snapshot.status === "present" ? snapshot.value : null
}

const sameSnapshot = (left: GenerationSnapshot, right: GenerationSnapshot) => {
  if (left.status !== right.status) return false
  if (left.status === "present" && right.status === "present") {
    return left.value.nonce === right.value.nonce && left.value.hash === right.value.hash
  }
  return left.status === "absent" && right.status === "absent"
}

const clearFailedRotation = () => {
  failedRotationGeneration = undefined
  failedRotationWasStale = false
  failedRotationSnapshot = undefined
}

const rememberFailedRotation = (
  before: GenerationSnapshot,
  wasStaleBefore: boolean,
  after: GenerationSnapshot,
  previousBoundGeneration: string | null
) => {
  boundGeneration = null
  if (failedRotationGeneration !== undefined && failedRotationGeneration !== null) {
    failedRotationWasStale =
      failedRotationWasStale ||
      wasStaleBefore ||
      failedRotationSnapshot === undefined ||
      !sameSnapshot(after, failedRotationSnapshot)
    return
  }
  if (before.status === "present" || before.status === "absent") {
    failedRotationGeneration = before.status === "present" ? before.value.nonce : null
    failedRotationSnapshot = before
    failedRotationWasStale = wasStaleBefore || !sameSnapshot(after, before)
    return
  }
  if (failedRotationGeneration === undefined) {
    failedRotationGeneration = previousBoundGeneration
    failedRotationSnapshot = before
    failedRotationWasStale = true
  } else {
    // The preceding snapshot check already latched this null marker as stale.
    failedRotationWasStale = true
  }
}
export const getBrowserSessionGeneration = () => readGeneration()?.nonce ?? null
let boundGeneration = getBrowserSessionGeneration()
const isStaleBrowserSessionBindingAt = (snapshot: GenerationSnapshot) => {
  if (failedRotationGeneration !== undefined) {
    // A failed write cannot regain ownership by observing a mismatch and then returning to the old snapshot.
    if (
      failedRotationWasStale ||
      failedRotationSnapshot === undefined ||
      !sameSnapshot(snapshot, failedRotationSnapshot)
    ) {
      failedRotationWasStale = true
      return true
    }
    return false
  }
  if (snapshot.status !== "present") return false
  return snapshot.value.nonce !== boundGeneration
}
export const isCurrentBrowserSession = () => {
  const snapshot = readGenerationSnapshot()
  if (
    (failedRotationGeneration !== undefined && isStaleBrowserSessionBindingAt(snapshot)) ||
    snapshot.status === "invalid" ||
    snapshot.status === "unavailable" ||
    failedRotationWasStale
  ) {
    return false
  }
  if (failedRotationGeneration !== undefined && failedRotationGeneration !== null) return false
  // A present snapshot after a null marker was rejected by the full-snapshot check above.
  const currentGeneration = snapshot.status === "present" ? snapshot.value.nonce : null
  return boundGeneration === currentGeneration
}
export const hasStaleBrowserSessionBinding = () =>
  isStaleBrowserSessionBindingAt(readGenerationSnapshot())
export const hasFailedBrowserSessionRotation = () => failedRotationGeneration !== undefined
export const acceptBrowserSessionGeneration = () => {
  const snapshot = readGenerationSnapshot()
  if (failedRotationGeneration !== undefined || failedRotationWasStale) {
    isStaleBrowserSessionBindingAt(snapshot)
    boundGeneration = null
    return
  }
  if (snapshot.status === "invalid" || snapshot.status === "unavailable") {
    const previousBoundGeneration = boundGeneration
    boundGeneration = null
    if (previousBoundGeneration !== null) {
      failedRotationGeneration = previousBoundGeneration
      failedRotationWasStale = true
      failedRotationSnapshot = snapshot
    }
    return
  }
  boundGeneration = snapshot.status === "present" ? snapshot.value.nonce : null
  clearFailedRotation()
}
export const matchesBrowserSession = (hash: string, nonce: string) => {
  const current = readGeneration()
  return current?.hash === hash && current.nonce === nonce
}
export const getSessionEpoch = () => epoch
export const invalidateSessionEpoch = () => {
  epoch += 1
}

/**
 * Begin an auth transition using a full storage snapshot as its ownership
 * receipt. Login may take over a stale but readable generation only after a
 * fresh nonce is written and read back exactly. Logout and unauthenticated MFA
 * require ownership before they may rotate. A failed write can continue online
 * only when the exact previously owned snapshot (or confirmed absence) remains.
 */
export const beginBrowserSessionTransition = (
  operation: BrowserSessionTransitionOperation
): BrowserSessionTransition => {
  const attempt = ++latestTransitionAttempt
  const before = readGenerationSnapshot()
  const staleBefore = isStaleBrowserSessionBindingAt(before)
  if (before.status === "invalid" || before.status === "unavailable") {
    return { status: "denied", isCurrent: () => false }
  }

  const generationBefore = before.status === "present" ? before.value.nonce : null
  const previousBoundGeneration = boundGeneration
  const absentWasOwned =
    before.status === "absent" &&
    boundGeneration === null &&
    !staleBefore &&
    (failedRotationGeneration === undefined ||
      (failedRotationGeneration === null &&
        !failedRotationWasStale &&
        failedRotationSnapshot?.status === "absent" &&
        sameSnapshot(before, failedRotationSnapshot)))
  const presentWasOwned =
    before.status === "present" &&
    !staleBefore &&
    ((failedRotationGeneration === undefined && boundGeneration === generationBefore) ||
      (failedRotationGeneration === generationBefore &&
        !failedRotationWasStale &&
        failedRotationSnapshot?.status === "present" &&
        sameSnapshot(before, failedRotationSnapshot)))
  const mayTakeOverStaleLogin = operation === "login" && before.status === "present" && staleBefore
  const mayBegin =
    before.status === "absent" ? absentWasOwned : presentWasOwned || mayTakeOverStaleLogin

  if (!mayBegin) return { status: "denied", isCurrent: () => false }

  let requestedNonce: string
  try {
    requestedNonce = crypto.randomUUID()
  } catch {
    return { status: "denied", isCurrent: () => false }
  }

  invalidateSessionEpoch()
  const transitionEpoch = epoch
  let writeFailed = false
  try {
    const storage = globalThis.localStorage
    if (!storage) throw new Error("Session storage is unavailable")
    storage.setItem(GENERATION_KEY, JSON.stringify({ nonce: requestedNonce, hash: null }))
  } catch {
    writeFailed = true
  }

  const after = readGenerationSnapshot()
  const verified =
    after.status === "present" && after.value.nonce === requestedNonce && after.value.hash === null

  if (verified) {
    boundGeneration = requestedNonce
    clearFailedRotation()
  } else {
    rememberFailedRotation(before, staleBefore, after, previousBoundGeneration)
  }

  const canContinueOnlineOnly =
    writeFailed && sameSnapshot(before, after) && (presentWasOwned || absentWasOwned)
  const status: BrowserSessionTransitionStatus = verified
    ? "verified"
    : canContinueOnlineOnly
      ? "online-only"
      : "denied"

  const isCurrent = () => {
    if (status === "denied" || latestTransitionAttempt !== attempt || epoch !== transitionEpoch)
      return false
    const current = readGenerationSnapshot()
    if (isStaleBrowserSessionBindingAt(current)) return false
    if (status === "verified") {
      return (
        current.status === "present" &&
        current.value.nonce === requestedNonce &&
        current.value.hash === null &&
        boundGeneration === requestedNonce &&
        failedRotationGeneration === undefined
      )
    }
    // The current snapshot check above and owned-snapshot checks below validate this receipt.
    if (before.status === "present") {
      return (
        failedRotationGeneration === before.value.nonce &&
        failedRotationSnapshot?.status === "present" &&
        sameSnapshot(failedRotationSnapshot, before) &&
        !failedRotationWasStale &&
        !isStaleBrowserSessionBindingAt(before)
      )
    }
    return (
      before.status === "absent" &&
      failedRotationGeneration === null &&
      failedRotationSnapshot?.status === "absent" &&
      sameSnapshot(failedRotationSnapshot, before) &&
      !failedRotationWasStale &&
      !isStaleBrowserSessionBindingAt(before)
    )
  }

  return { status, isCurrent }
}

export const rotateBrowserSession = () => {
  const before = readGenerationSnapshot()
  const previousBoundGeneration = boundGeneration
  const wasStaleBeforeRotation = isStaleBrowserSessionBindingAt(before)
  invalidateSessionEpoch()

  let nonce: string
  try {
    nonce = crypto.randomUUID()
  } catch {
    rememberFailedRotation(
      before,
      wasStaleBeforeRotation,
      readGenerationSnapshot(),
      previousBoundGeneration
    )
    return
  }

  try {
    const storage = globalThis.localStorage
    if (!storage) throw new Error("Session storage is unavailable")
    storage.setItem(GENERATION_KEY, JSON.stringify({ nonce, hash: null }))
  } catch {
    // A subsequent exact readback still decides whether the transition landed.
  }

  const after = readGenerationSnapshot()
  if (after.status === "present" && after.value.nonce === nonce && after.value.hash === null) {
    boundGeneration = nonce
    clearFailedRotation()
    return
  }

  rememberFailedRotation(before, wasStaleBeforeRotation, after, previousBoundGeneration)
}
export const establishBrowserSession = (
  hash: string,
  expectedGeneration: string | null
): string | null => {
  try {
    if (failedRotationGeneration !== undefined || failedRotationWasStale) return null
    const current = readGeneration()
    if ((current?.nonce ?? null) !== expectedGeneration) return null
    const nonce =
      current?.hash === hash || current?.hash === null ? current.nonce : crypto.randomUUID()
    globalThis.localStorage.setItem(GENERATION_KEY, JSON.stringify({ nonce, hash }))
    const after = readGenerationSnapshot()
    if (after.status !== "present" || after.value.nonce !== nonce || after.value.hash !== hash) {
      return null
    }
    boundGeneration = nonce
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
