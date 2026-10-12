import { createHash, randomUUID } from "node:crypto"
import { createRequire } from "node:module"
import { mkdir, open, lstat, readFile, readdir, realpath, rename, unlink } from "node:fs/promises"
import { isAbsolute, join, resolve } from "node:path"
import { fileURLToPath } from "node:url"

export const REGISTRATION_WINDOW_MS = 60_000
export const REGISTRATION_CADENCE_MS = 13_000
export const REGISTRATION_MAX_COST = 5
export const REGISTRATION_MAX_TEST_TIMEOUT_MS = 360_000
export const REGISTRATION_UNKNOWN_DRAIN_MS = 60_000

const MAX_CLOCK_SKEW_MS = 5_000
const DEADLINE_MARGIN_MS = 1_000
const MIN_ACTION_RESERVE_MS = 15_000
const MAX_LEDGER_BYTES = 4_096
const MAX_OWNER_BYTES = 65_536
const MODULE_REPOSITORY_ROOT = fileURLToPath(new URL("../../", import.meta.url))
const PLAYWRIGHT_CORE_REQUIRE = createRequire(import.meta.url)
const LEDGER_DIRECTORY = ".live-registration-admission"
const LEDGER_FILE = "ledger.json"

const LEDGER_KEYS = ["events", "ownerBinding", "pending", "updatedAtMs", "version"]
const EVENT_KEYS = ["completedAtMs", "cost"]
const PENDING_KEYS = ["cost", "startedAtMs"]

function isRecord(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function hasExactKeys(value, expected) {
  return isRecord(value) && Object.keys(value).sort().join("\0") === [...expected].sort().join("\0")
}

function comparablePath(value, platform = process.platform) {
  const normalized = resolve(value)
  return platform === "win32" ? normalized.toLowerCase() : normalized
}

function samePath(left, right, platform = process.platform) {
  return comparablePath(left, platform) === comparablePath(right, platform)
}

export function resolveLiveRegistrationStateRoot(
  environment = process.env,
  liveWorktreeRoot = MODULE_REPOSITORY_ROOT,
  platform = process.platform
) {
  const worktreeRoot = resolve(liveWorktreeRoot)
  const primaryRoot = environment.LIVE_PRIMARY_REPOSITORY_ROOT
  if (typeof primaryRoot !== "string" || !isAbsolute(primaryRoot)) {
    throw new Error("live registration admission requires the verified primary repository binding")
  }

  const inPlaceRoot = environment.LIVE_STAND_STATE_ROOT
  if (inPlaceRoot !== undefined) {
    if (
      typeof inPlaceRoot !== "string" ||
      inPlaceRoot.trim() === "" ||
      !isAbsolute(inPlaceRoot) ||
      !samePath(primaryRoot, worktreeRoot, platform)
    ) {
      throw new Error("live registration admission has an invalid in-place owner binding")
    }
    return resolve(inPlaceRoot)
  }

  if (samePath(primaryRoot, worktreeRoot, platform)) {
    throw new Error("live registration admission has an invalid legacy worktree binding")
  }
  return worktreeRoot
}

function assertPrivatePosixMode(details, expectedMode, description) {
  if (process.platform === "win32") return
  if (
    (typeof process.getuid === "function" && details.uid !== process.getuid()) ||
    (details.mode & 0o777) !== expectedMode
  ) {
    throw new Error("live registration admission " + description + " is not private")
  }
}

function requireSafeInteger(value, name) {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new Error("live registration admission has invalid " + name)
  }
  return value
}

function normalizeTimestamp(value, nowMs, name) {
  const timestamp = requireSafeInteger(value, name)
  if (timestamp > nowMs + MAX_CLOCK_SKEW_MS) {
    throw new Error("live registration admission has an out-of-range " + name)
  }
  return Math.min(timestamp, nowMs)
}

function assertEvent(event, nowMs) {
  if (!hasExactKeys(event, EVENT_KEYS)) {
    throw new Error("live registration admission has a malformed event")
  }
  if (event.cost !== 1 && event.cost !== 2) {
    throw new Error("live registration admission has an invalid event cost")
  }
  return {
    completedAtMs: normalizeTimestamp(event.completedAtMs, nowMs, "completion time"),
    cost: event.cost,
  }
}

export function validateRegistrationLedger(value, ownerBinding, nowMs = Date.now()) {
  if (!hasExactKeys(value, LEDGER_KEYS) || value.version !== 1) {
    throw new Error("live registration admission ledger is malformed")
  }
  if (
    typeof ownerBinding !== "string" ||
    !/^[a-f0-9]{64}$/u.test(ownerBinding) ||
    value.ownerBinding !== ownerBinding
  ) {
    throw new Error("live registration admission ledger owner does not match")
  }

  const updatedAtMs = normalizeTimestamp(value.updatedAtMs, nowMs, "ledger timestamp")
  if (!Array.isArray(value.events) || value.events.length > REGISTRATION_MAX_COST) {
    throw new Error("live registration admission ledger event list is invalid")
  }

  const events = value.events.map((event) => assertEvent(event, nowMs))
  let previousCompletion = 0
  let activeCost = 0
  for (const event of events) {
    if (event.completedAtMs < previousCompletion || event.completedAtMs > updatedAtMs) {
      throw new Error("live registration admission ledger events are out of order")
    }
    previousCompletion = event.completedAtMs
    activeCost += event.cost
  }
  if (activeCost > REGISTRATION_MAX_COST) {
    throw new Error("live registration admission ledger exceeds its rolling budget")
  }

  let pending = null
  if (value.pending !== null) {
    if (!hasExactKeys(value.pending, PENDING_KEYS)) {
      throw new Error("live registration admission pending state is malformed")
    }
    const startedAtMs = normalizeTimestamp(value.pending.startedAtMs, nowMs, "reservation time")
    const cost = value.pending.cost
    if (cost !== 0 && cost !== 1 && cost !== 2) {
      throw new Error("live registration admission pending cost is invalid")
    }
    if (startedAtMs > updatedAtMs) {
      throw new Error("live registration admission reservation is newer than its ledger")
    }
    pending = { startedAtMs, cost }
  }

  return { version: 1, ownerBinding, updatedAtMs, pending, events }
}

export function computeRegistrationWaitMs(events, cost, nowMs = Date.now()) {
  requireSafeInteger(nowMs, "clock")
  if (cost !== 1 && cost !== 2) {
    throw new Error("live registration admission request cost must be one or two")
  }

  const normalizedEvents = events.map((event) => assertEvent(event, nowMs))
  let targetAtMs = nowMs
  if (normalizedEvents.length > 0) {
    targetAtMs = Math.max(
      targetAtMs,
      normalizedEvents[normalizedEvents.length - 1].completedAtMs + REGISTRATION_CADENCE_MS
    )
  }

  while (true) {
    const activeEvents = normalizedEvents.filter(
      (event) => event.completedAtMs > targetAtMs - REGISTRATION_WINDOW_MS
    )
    const activeCost = activeEvents.reduce((total, event) => total + event.cost, 0)
    if (activeCost + cost <= REGISTRATION_MAX_COST) {
      return Math.max(0, targetAtMs - nowMs)
    }
    const earliest = activeEvents[0]
    if (!earliest) {
      throw new Error("live registration admission could not resolve its rolling window")
    }
    targetAtMs = Math.max(targetAtMs, earliest.completedAtMs + REGISTRATION_WINDOW_MS)
  }
}

/**
 * Samples both clocks around Playwright's pinned worker clock read. The returned
 * local deadline is conservative because localBeforeMs precedes playwrightNowMs.
 */
function samplePlaywrightDeadlineClockPair() {
  let localBeforeMs
  let playwrightNowMs
  let localAfterMs
  try {
    localBeforeMs = performance.now()
    const coreBundle = PLAYWRIGHT_CORE_REQUIRE("playwright-core/lib/coreBundle")
    const iso = Reflect.get(coreBundle, "iso")
    const monotonicTime = isRecord(iso) ? Reflect.get(iso, "monotonicTime") : null
    if (typeof monotonicTime !== "function") return null
    playwrightNowMs = Reflect.apply(monotonicTime, iso, [])
    localAfterMs = performance.now()
  } catch {
    return null
  }

  if (
    !Number.isFinite(localBeforeMs) ||
    !Number.isFinite(playwrightNowMs) ||
    !Number.isFinite(localAfterMs) ||
    localBeforeMs < 0 ||
    localAfterMs < localBeforeMs
  ) {
    return null
  }
  return { localBeforeMs, playwrightNowMs, localAfterMs }
}

/**
 * Reads the pinned Playwright TestInfo slot and translates its active deadline
 * into this process's performance.now() domain. TestInfo exposes no public
 * current deadline; fail closed if the pinned slot or clock shape changes.
 */
export function readPlaywrightTestSlotDeadlineAtMs(
  testInfo,
  maximumTimeoutMs = REGISTRATION_MAX_TEST_TIMEOUT_MS,
  sampleClockPair = samplePlaywrightDeadlineClockPair
) {
  if (
    !Number.isSafeInteger(maximumTimeoutMs) ||
    maximumTimeoutMs < 1 ||
    !isRecord(testInfo) ||
    typeof sampleClockPair !== "function"
  ) {
    return null
  }

  let timeoutMs
  let deadlineMethod
  try {
    timeoutMs = Reflect.get(testInfo, "timeout")
    deadlineMethod = Reflect.get(testInfo, "_deadline")
  } catch {
    return null
  }
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0 || timeoutMs > maximumTimeoutMs) {
    return null
  }
  if (typeof deadlineMethod !== "function") return null

  let slot
  try {
    slot = Reflect.apply(deadlineMethod, testInfo, [])
  } catch {
    return null
  }
  if (!isRecord(slot)) return null

  let deadlineAtMs
  let slotTimeoutMs
  try {
    deadlineAtMs = Reflect.get(slot, "deadline")
    slotTimeoutMs = Reflect.get(slot, "timeout")
  } catch {
    return null
  }
  if (
    typeof deadlineAtMs !== "number" ||
    !Number.isFinite(deadlineAtMs) ||
    slotTimeoutMs !== timeoutMs
  ) {
    return null
  }

  let clockPair
  try {
    clockPair = Reflect.apply(sampleClockPair, undefined, [])
  } catch {
    return null
  }
  if (!isRecord(clockPair)) return null

  let localBeforeMs
  let playwrightNowMs
  let localAfterMs
  try {
    localBeforeMs = Reflect.get(clockPair, "localBeforeMs")
    playwrightNowMs = Reflect.get(clockPair, "playwrightNowMs")
    localAfterMs = Reflect.get(clockPair, "localAfterMs")
  } catch {
    return null
  }
  if (
    !Number.isFinite(localBeforeMs) ||
    !Number.isFinite(playwrightNowMs) ||
    !Number.isFinite(localAfterMs) ||
    localBeforeMs < 0 ||
    localAfterMs < localBeforeMs
  ) {
    return null
  }

  const remainingMs = deadlineAtMs - playwrightNowMs
  if (!Number.isFinite(remainingMs) || remainingMs <= 0 || remainingMs > timeoutMs + 1) {
    return null
  }

  const translatedDeadlineAtMs = localBeforeMs + remainingMs
  if (!Number.isFinite(translatedDeadlineAtMs) || translatedDeadlineAtMs <= localAfterMs) {
    return null
  }
  return translatedDeadlineAtMs
}

export function assertRegistrationWaitFits(
  waitMs,
  deadlineAtMs,
  nowMonotonicMs = performance.now()
) {
  requireSafeInteger(waitMs, "wait")
  if (!Number.isFinite(deadlineAtMs) || deadlineAtMs <= 0 || !Number.isFinite(nowMonotonicMs)) {
    throw new Error("live registration admission cannot read the current test deadline")
  }

  const remainingMs = deadlineAtMs - nowMonotonicMs
  if (waitMs + MIN_ACTION_RESERVE_MS + DEADLINE_MARGIN_MS > remainingMs) {
    throw new Error("live registration admission cannot fit the existing test deadline")
  }
  return remainingMs
}

async function delay(milliseconds) {
  if (milliseconds > 0) {
    await new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds))
  }
}

async function assertRealDirectory(path) {
  const details = await lstat(path)
  if (!details.isDirectory() || details.isSymbolicLink()) {
    throw new Error("live registration admission state directory is unsafe")
  }
  const actual = await realpath(path)
  if (!samePath(actual, path)) {
    throw new Error("live registration admission state directory is redirected")
  }
  return actual
}

async function readOwnerBinding(stateRoot) {
  if (!isAbsolute(stateRoot)) {
    throw new Error("live registration admission state root must be absolute")
  }
  const realRoot = await assertRealDirectory(resolve(stateRoot))
  const secretsDirectory = join(realRoot, ".secrets")
  const realSecretsDirectory = await assertRealDirectory(secretsDirectory)
  if (!samePath(realSecretsDirectory, secretsDirectory)) {
    throw new Error("live registration admission owner directory is redirected")
  }

  const markerPath = join(realSecretsDirectory, "live-stand.json")
  const markerStat = await lstat(markerPath)
  if (
    !markerStat.isFile() ||
    markerStat.isSymbolicLink() ||
    markerStat.size < 1 ||
    markerStat.size > MAX_OWNER_BYTES
  ) {
    throw new Error("live registration admission signed owner marker is unsafe")
  }
  if (!samePath(await realpath(markerPath), markerPath)) {
    throw new Error("live registration admission signed owner marker is redirected")
  }

  let owner
  try {
    owner = JSON.parse(await readFile(markerPath, "utf8"))
  } catch {
    throw new Error("live registration admission signed owner marker is invalid")
  }
  if (
    !isRecord(owner) ||
    !Number.isSafeInteger(owner.version) ||
    owner.version < 3 ||
    owner.version > 11 ||
    typeof owner.repository !== "string" ||
    !isAbsolute(owner.repository) ||
    typeof owner.worktree !== "string" ||
    !isAbsolute(owner.worktree) ||
    !samePath(owner.worktree, realRoot) ||
    typeof owner.project_name !== "string" ||
    !/^ue-live-[a-f0-9]{16}$/u.test(owner.project_name) ||
    typeof owner.signature !== "string" ||
    !/^[a-f0-9]{64}$/u.test(owner.signature) ||
    (owner.source_sha !== undefined &&
      owner.source_sha !== null &&
      (typeof owner.source_sha !== "string" || !/^[a-f0-9]{40}$/u.test(owner.source_sha)))
  ) {
    throw new Error("live registration admission signed owner binding is invalid")
  }

  const expectedRepository = process.env.LIVE_PRIMARY_REPOSITORY_ROOT
  if (
    typeof expectedRepository !== "string" ||
    !isAbsolute(expectedRepository) ||
    !samePath(owner.repository, expectedRepository)
  ) {
    throw new Error("live registration admission repository owner does not match")
  }

  const ownerIdentity = JSON.stringify([
    owner.version,
    comparablePath(owner.repository),
    comparablePath(realRoot),
    owner.project_name,
  ])
  const ownerBinding = createHash("sha256").update(ownerIdentity, "utf8").digest("hex")
  return { realRoot, ownerBinding }
}

async function admissionPaths(stateRoot, { createDirectory = false } = {}) {
  const { realRoot, ownerBinding } = await readOwnerBinding(stateRoot)
  const directory = join(realRoot, ".secrets", LEDGER_DIRECTORY)
  if (createDirectory) {
    try {
      await mkdir(directory, { mode: 0o700 })
    } catch (error) {
      if (error?.code !== "EEXIST") {
        throw new Error("live registration admission directory could not be created", {
          cause: error,
        })
      }
    }
  }
  const realDirectory = await assertRealDirectory(directory)
  assertPrivatePosixMode(await lstat(realDirectory), 0o700, "ledger directory")
  if (!samePath(realDirectory, directory)) {
    throw new Error("live registration admission directory is redirected")
  }
  const entries = await readdir(realDirectory)
  if (entries.some((entry) => entry !== LEDGER_FILE)) {
    throw new Error("live registration admission directory contains unexpected files")
  }
  return { directory: realDirectory, ledgerPath: join(realDirectory, LEDGER_FILE), ownerBinding }
}

async function readLedger(paths, nowMs = Date.now(), { allowMissing = false } = {}) {
  let fileInfo
  try {
    fileInfo = await lstat(paths.ledgerPath)
  } catch (error) {
    if (error?.code === "ENOENT" && allowMissing) return null
    throw new Error("live registration admission ledger is unavailable", { cause: error })
  }
  if (
    !fileInfo.isFile() ||
    fileInfo.isSymbolicLink() ||
    fileInfo.size < 1 ||
    fileInfo.size > MAX_LEDGER_BYTES ||
    (fileInfo.nlink !== undefined && fileInfo.nlink !== 1) ||
    !samePath(await realpath(paths.ledgerPath), paths.ledgerPath)
  ) {
    throw new Error("live registration admission ledger file is unsafe")
  }

  assertPrivatePosixMode(fileInfo, 0o600, "ledger file")

  let parsed
  try {
    parsed = JSON.parse(await readFile(paths.ledgerPath, "utf8"))
  } catch {
    throw new Error("live registration admission ledger is malformed")
  }
  return validateRegistrationLedger(parsed, paths.ownerBinding, nowMs)
}

async function writeLedger(paths, ledger) {
  const normalized = validateRegistrationLedger(ledger, paths.ownerBinding, Date.now())
  const temporaryPath = join(paths.directory, "ledger-" + randomUUID() + ".tmp")
  let handle
  try {
    handle = await open(temporaryPath, "wx", 0o600)
    await handle.writeFile(JSON.stringify(normalized) + "\n", "utf8")
    await handle.sync()
    await handle.close()
    handle = undefined
    await rename(temporaryPath, paths.ledgerPath)
  } catch {
    if (handle) await handle.close().catch(() => undefined)
    await unlink(temporaryPath).catch(() => undefined)
    throw new Error("live registration admission ledger could not be persisted")
  }
}

function pruneEvents(events, nowMs) {
  return events.filter((event) => event.completedAtMs > nowMs - REGISTRATION_WINDOW_MS)
}

function ownerBoundLedger(ownerBinding, updatedAtMs, events, pending) {
  return { version: 1, ownerBinding, updatedAtMs, pending, events }
}

export async function initializeLiveRegistrationAdmission(
  stateRoot,
  { now = Date.now, sleep = delay } = {}
) {
  const paths = await admissionPaths(stateRoot, { createDirectory: true })
  let ledger = await readLedger(paths, now(), { allowMissing: true })
  if (ledger === null) {
    const initialNow = now()
    ledger = ownerBoundLedger(paths.ownerBinding, initialNow, [], {
      startedAtMs: initialNow,
      cost: 0,
    })
    await writeLedger(paths, ledger)
  }

  if (ledger.pending !== null) {
    const pending = ledger.pending
    await sleep(REGISTRATION_UNKNOWN_DRAIN_MS)
    const currentBinding = await readOwnerBinding(stateRoot)
    if (currentBinding.ownerBinding !== paths.ownerBinding) {
      throw new Error("live registration admission owner changed during its quiet interval")
    }
    const currentPaths = await admissionPaths(stateRoot)
    const current = await readLedger(currentPaths, now())
    if (
      current.pending === null ||
      current.pending.startedAtMs !== pending.startedAtMs ||
      current.pending.cost !== pending.cost
    ) {
      throw new Error("live registration admission pending state changed during its quiet interval")
    }
    const completedAtMs = now()
    await writeLedger(
      currentPaths,
      ownerBoundLedger(
        currentPaths.ownerBinding,
        completedAtMs,
        pruneEvents(current.events, completedAtMs),
        null
      )
    )
  }
}

let activeReservation = false

function isOwnedRegistrationRequest(request, origin) {
  try {
    const url = new URL(request.url())
    return (
      request.method() === "POST" &&
      url.origin === origin &&
      url.pathname === "/api/v1/auth/register" &&
      url.search === "" &&
      url.hash === ""
    )
  } catch {
    return false
  }
}

function requirePageOrigin(page) {
  const liveBaseUrl = process.env.LIVE_BASE_URL
  if (typeof liveBaseUrl !== "string" || liveBaseUrl.trim() === "") {
    throw new Error("live registration admission requires the verified live base URL")
  }
  let expectedOrigin
  let pageOrigin
  try {
    expectedOrigin = new URL(liveBaseUrl).origin
    pageOrigin = new URL(page.url()).origin
  } catch {
    throw new Error("live registration admission cannot resolve the page origin")
  }
  if (pageOrigin !== expectedOrigin) {
    throw new Error("live registration admission requires the owned live application page")
  }
  return expectedOrigin
}

function waitForTrackedRequests(activeRequests, changed, deadlineAtMs) {
  if (activeRequests.size === 0) return Promise.resolve(true)
  const remaining = Math.floor(deadlineAtMs - performance.now() - DEADLINE_MARGIN_MS)
  if (remaining <= 0) return Promise.resolve(false)
  return new Promise((resolvePromise) => {
    let timer
    const finish = (settled) => {
      if (timer !== undefined) clearTimeout(timer)
      const index = changed.indexOf(onChanged)
      if (index >= 0) changed.splice(index, 1)
      resolvePromise(settled)
    }
    const onChanged = () => finish(true)
    changed.push(onChanged)
    timer = setTimeout(() => finish(false), remaining)
  })
}

export async function runLiveRegistrationAdmission(page, deadlineAtMs, cost, action) {
  if (activeReservation) {
    throw new Error("live registration admission cannot overlap registration callbacks")
  }
  if ((cost !== 1 && cost !== 2) || typeof action !== "function") {
    throw new Error("live registration admission received an invalid reservation")
  }
  activeReservation = true
  try {
    return await runLiveRegistrationAdmissionExclusive(page, deadlineAtMs, cost, action)
  } finally {
    activeReservation = false
  }
}

async function runLiveRegistrationAdmissionExclusive(page, deadlineAtMs, cost, action) {
  const origin = requirePageOrigin(page)
  const stateRoot = resolveLiveRegistrationStateRoot()
  const paths = await admissionPaths(stateRoot)
  let ledger = await readLedger(paths)
  let nowMs = Date.now()

  if (ledger.pending !== null) {
    assertRegistrationWaitFits(REGISTRATION_UNKNOWN_DRAIN_MS, deadlineAtMs, performance.now())
    await delay(REGISTRATION_UNKNOWN_DRAIN_MS)
    const currentPaths = await admissionPaths(stateRoot)
    const current = await readLedger(currentPaths)
    if (
      currentPaths.ownerBinding !== paths.ownerBinding ||
      current.pending === null ||
      current.pending.startedAtMs !== ledger.pending.startedAtMs ||
      current.pending.cost !== ledger.pending.cost
    ) {
      throw new Error("live registration admission pending state changed during its quiet interval")
    }
    nowMs = Date.now()
    await writeLedger(
      currentPaths,
      ownerBoundLedger(currentPaths.ownerBinding, nowMs, pruneEvents(current.events, nowMs), null)
    )
    ledger = await readLedger(currentPaths)
  }

  const waitMs = computeRegistrationWaitMs(pruneEvents(ledger.events, nowMs), cost, nowMs)
  assertRegistrationWaitFits(waitMs, deadlineAtMs, performance.now())
  if (waitMs > 0) await delay(waitMs)

  let reservationPaths = await admissionPaths(stateRoot)
  if (reservationPaths.ownerBinding !== paths.ownerBinding) {
    throw new Error("live registration admission owner changed before submit")
  }
  ledger = await readLedger(reservationPaths)

  let reservedAtMs
  while (true) {
    if (ledger.pending !== null) {
      throw new Error("live registration admission has an unresolved prior request")
    }
    nowMs = Date.now()
    const remainingWaitMs = computeRegistrationWaitMs(
      pruneEvents(ledger.events, nowMs),
      cost,
      nowMs
    )
    if (remainingWaitMs === 0) {
      reservedAtMs = nowMs
      break
    }
    assertRegistrationWaitFits(remainingWaitMs, deadlineAtMs, performance.now())
    await delay(remainingWaitMs)
    reservationPaths = await admissionPaths(stateRoot)
    if (reservationPaths.ownerBinding !== paths.ownerBinding) {
      throw new Error("live registration admission owner changed before submit")
    }
    ledger = await readLedger(reservationPaths)
  }

  assertRegistrationWaitFits(0, deadlineAtMs, performance.now())
  const pruned = pruneEvents(ledger.events, reservedAtMs)
  await writeLedger(
    reservationPaths,
    ownerBoundLedger(reservationPaths.ownerBinding, reservedAtMs, pruned, {
      startedAtMs: reservedAtMs,
      cost,
    })
  )

  const activeRequests = new Map()
  const changeListeners = []
  let requestCount = 0
  let latestCompletionAtMs = reservedAtMs
  const onRequest = (request) => {
    if (!isOwnedRegistrationRequest(request, origin)) return
    requestCount += 1
    activeRequests.set(request, true)
  }
  const onRequestComplete = (request) => {
    if (!activeRequests.delete(request)) return
    latestCompletionAtMs = Math.max(latestCompletionAtMs, Date.now())
    for (const notify of changeListeners.splice(0)) notify()
  }

  page.on("request", onRequest)
  page.on("requestfinished", onRequestComplete)
  page.on("requestfailed", onRequestComplete)

  let value
  let actionError
  let actionFailed = false
  try {
    try {
      value = await action()
    } catch (error) {
      actionFailed = true
      actionError = error
    }

    await new Promise((resolvePromise) => setTimeout(resolvePromise, 0))
    while (activeRequests.size > 0) {
      const settled = await waitForTrackedRequests(activeRequests, changeListeners, deadlineAtMs)
      if (!settled) break
    }

    const completedKnownRequest = requestCount > 0 && activeRequests.size === 0
    if (completedKnownRequest && requestCount <= cost) {
      const completedAtMs = Math.max(latestCompletionAtMs, Date.now())
      const completionPaths = await admissionPaths(stateRoot)
      if (completionPaths.ownerBinding !== reservationPaths.ownerBinding) {
        throw new Error("live registration admission owner changed after submit")
      }
      const latest = await readLedger(completionPaths)
      if (
        latest.pending === null ||
        latest.pending.startedAtMs !== reservedAtMs ||
        latest.pending.cost !== cost
      ) {
        throw new Error("live registration admission reservation changed after submit")
      }
      const events = pruneEvents(latest.events, completedAtMs)
      events.push({ completedAtMs, cost })
      await writeLedger(
        completionPaths,
        ownerBoundLedger(completionPaths.ownerBinding, completedAtMs, events, null)
      )
    } else {
      const current = await readLedger(await admissionPaths(stateRoot))
      if (current.pending === null) {
        throw new Error("live registration admission lost its fail-closed reservation")
      }
      if (!actionFailed) {
        throw new Error("live registration admission could not confirm a completed request")
      }
    }

    if (actionFailed) throw actionError
    return value
  } finally {
    page.off("request", onRequest)
    page.off("requestfinished", onRequestComplete)
    page.off("requestfailed", onRequestComplete)
  }
}
