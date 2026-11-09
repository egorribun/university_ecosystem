/// <reference lib="webworker" />
declare const self: ServiceWorkerGlobalScope

import { openDB, type IDBPDatabase } from "idb"
import { warn } from "./logger"
import {
  NOTIFICATION_INTERACTIONS_DB_NAME as CLICK_DB_NAME,
  NOTIFICATION_INTERACTIONS_DB_VERSION as DB_VERSION,
} from "../constants/notificationInteractionsDb"
import { OFFLINE_DEAD_LETTER_MESSAGE_TYPE } from "../constants/serviceWorkerMessages"
import { requestReplayCredentials } from "./replayCredentials"
import {
  claimReplayLease,
  releaseReplayLease,
  renewReplayLease,
  REPLAY_ACTIVE_ATTEMPT_KEY,
  REPLAY_LEASE_KEY,
  REPLAY_LEASE_STORE,
  type ReplayActiveAttemptRecord,
  type ReplayLeaseRecord,
} from "./replayLease"
import {
  isExpiredOtherSessionRecord,
  isRetryableReplayStatus,
  REPLAY_LEASE_POLL_MS,
  REPLAY_LEASE_RENEW_MS,
  REPLAY_MAX_ATTEMPTS,
  REPLAY_REQUEST_TIMEOUT_MS,
  replayBackoffMs,
} from "./replayPolicy"
import { broadcastMessage } from "./utils"

export const STORES = {
  NAVIGATION: "pending-navigations",
  REPORT: "pending-reports",
  NEWS_INTERACTION: "pending-news-interactions",
  MUTATION: "pending-mutations",
} as const

export interface PendingMutationRecord {
  id?: number
  mutationId: string
  url: string
  method: "POST" | "PUT" | "PATCH" | "DELETE"
  payload: unknown
  headers?: Record<string, string>
  timestamp: number
  idempotencyKey: string
  dedupeKey?: string
  retryCount: number
  category?: "events" | "news" | "messenger" | "profile" | "schedule" | "general"
  /** Browser session nonce the record was created under. Absent or null records are held, never replayed. */
  sessionNonce?: string | null
  /** Earliest epoch-millisecond time of the next replay attempt after a retryable failure. */
  nextAttemptAt?: number
}

/**
 * Get the database with proper upgrade handler.
 * All functions should use this instead of openDB directly.
 */
async function getDatabase() {
  const connection: IDBPDatabase = await openDB(CLICK_DB_NAME, DB_VERSION, {
    upgrade(db, _oldVersion, _newVersion, transaction) {
      if (!db.objectStoreNames.contains(STORES.NAVIGATION)) {
        db.createObjectStore(STORES.NAVIGATION, { keyPath: "id", autoIncrement: true })
      }
      if (!db.objectStoreNames.contains(STORES.REPORT)) {
        const reportStore = db.createObjectStore(STORES.REPORT, {
          keyPath: "id",
          autoIncrement: true,
        })
        // DEBT-04 (audit Wave 11): deduplication index for idempotent requests.
        reportStore.createIndex("dedupeKey", "dedupeKey", { unique: false })
      } else {
        // Upgrade: add dedupeKey index using the active versionchange transaction.
        // db.transaction() cannot be called during onupgradeneeded — only the
        // implicit upgrade transaction is valid here. Because DB_VERSION is 5,
        // an upgrade callback with an existing store necessarily comes from an
        // older version.
        const store = transaction.objectStore(STORES.REPORT)
        if (!store.indexNames.contains("dedupeKey")) {
          store.createIndex("dedupeKey", "dedupeKey", { unique: false })
        }
      }
      if (!db.objectStoreNames.contains(STORES.NEWS_INTERACTION)) {
        db.createObjectStore(STORES.NEWS_INTERACTION, { keyPath: "id", autoIncrement: true })
      }
      if (!db.objectStoreNames.contains(STORES.MUTATION)) {
        const mutationStore = db.createObjectStore(STORES.MUTATION, {
          keyPath: "id",
          autoIncrement: true,
        })
        mutationStore.createIndex("mutationId", "mutationId", { unique: true })
        mutationStore.createIndex("category", "category", { unique: false })
        mutationStore.createIndex("dedupeKey", "dedupeKey", { unique: false })
      }
      // Version 5: the lease row is added to an existing database without touching the queues.
      if (!db.objectStoreNames.contains(REPLAY_LEASE_STORE)) {
        db.createObjectStore(REPLAY_LEASE_STORE, { keyPath: "id" })
      }
    },
    // An open connection from an older page or worker must not hold the schema upgrade
    // hostage. Closing it lets this version open; the next operation reopens on demand.
    blocking() {
      connection.close()
    },
  })
  return connection
}

/**
 * DEBT-04 (audit Wave 11): Compute a SHA-256 fingerprint of a pending request for
 * deduplication.  Idempotent methods (PUT, DELETE, HEAD) with the same URL+body
 * should only appear once in the queue.  POST requests use a random idempotency
 * key generated at enqueue time instead.
 */
async function digestKey(input: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(input))
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
}

/**
 * Initialize IndexedDB for offline interaction queue.
 */
export async function initOfflineQueue() {
  await getDatabase()
}

function isOnline(): boolean {
  return self.navigator.onLine !== false
}

export async function addRecord<T extends object>(storeName: string, value: T) {
  const db = await getDatabase()
  return db.add(storeName, value)
}

export async function storePendingNavigation(record: {
  url: string
  timestamp: number
  sessionNonce?: string | null
}) {
  return addRecord(STORES.NAVIGATION, { ...record, sessionNonce: record.sessionNonce ?? null })
}

export async function readPendingNavigations() {
  const db = await getDatabase()
  return db.getAll(STORES.NAVIGATION)
}

export async function storePendingReport(record: {
  url: string
  reportUrl: string
  timestamp: number
  payload?: unknown
  method?: string
  sessionNonce?: string | null
}) {
  const method = (record.method ?? "POST").toUpperCase()
  const sessionNonce = record.sessionNonce ?? null
  const idempotentMethods = ["GET", "PUT", "DELETE", "HEAD"]

  if (idempotentMethods.includes(method)) {
    // DEBT-04 (audit Wave 11): deduplicate idempotent requests by a framed
    // method+URL+body+session tuple so different methods, field boundaries and
    // browser sessions cannot collide. A user going offline then back online while
    // the same resource is pending should not enqueue duplicate requests that create
    // duplicate side-effects.
    const dedupeKey = await digestKey(
      JSON.stringify([method, record.reportUrl, record.payload ?? null, sessionNonce])
    )
    const db = await getDatabase()
    const existing = await db.getAllFromIndex(STORES.REPORT, "dedupeKey", dedupeKey)
    if (existing.length > 0) {
      return // already queued — skip
    }
    return db.add(STORES.REPORT, { ...record, method, dedupeKey, sessionNonce })
  }

  // POST (and other non-idempotent): always enqueue; attach a random idempotency
  // key so the server can deduplicate retries on its side (via Idempotency-Key header).
  const idempotencyKey = crypto.randomUUID()
  return addRecord(STORES.REPORT, { ...record, method, idempotencyKey, sessionNonce })
}

export async function readPendingReports() {
  const db = await getDatabase()
  return db.getAll(STORES.REPORT)
}

/** Keys that could enable prototype pollution — always blocked. */
const BLOCKED_PAYLOAD_KEYS = new Set(["__proto__", "constructor", "prototype"])
/** Maximum recursion depth to prevent stack overflow on adversarial input. */
const MAX_SANITIZE_DEPTH = 10
/** Maximum array length to include (truncate beyond this). */
const MAX_ARRAY_LENGTH = 100

export function sanitizeReportPayload(payload: unknown, _depth = 0): unknown {
  if (_depth > MAX_SANITIZE_DEPTH) return "[truncated]"
  if (!payload || typeof payload !== "object") return payload

  if (Array.isArray(payload)) {
    // Truncate oversized arrays to prevent DoS via unbounded allocation
    return payload.slice(0, MAX_ARRAY_LENGTH).map((item) => sanitizeReportPayload(item, _depth + 1))
  }

  const result: Record<string, unknown> = Object.create(null)
  const source = payload as Record<string, unknown>

  // Object.keys only returns own enumerable properties, never prototype chain —
  // safer than for...in which traverses the full prototype chain even with hasOwnProperty.
  for (const key of Object.keys(source)) {
    if (BLOCKED_PAYLOAD_KEYS.has(key)) continue
    const val = source[key]
    if (typeof val === "function") continue
    result[key] = sanitizeReportPayload(val, _depth + 1)
  }
  return result
}

export async function storePendingMutation(
  record: Omit<
    PendingMutationRecord,
    "mutationId" | "idempotencyKey" | "timestamp" | "retryCount"
  > &
    Partial<PendingMutationRecord>
) {
  const fullRecord: PendingMutationRecord = {
    mutationId:
      record.mutationId ??
      (typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : String(Date.now() + Math.random())),
    url: record.url,
    method: record.method ?? "POST",
    payload: sanitizeReportPayload(record.payload),
    headers: record.headers,
    timestamp: record.timestamp ?? Date.now(),
    idempotencyKey:
      record.idempotencyKey ??
      (typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : String(Date.now() + Math.random())),
    retryCount: record.retryCount ?? 0,
    category: record.category ?? "general",
    sessionNonce: record.sessionNonce ?? null,
  }
  return addRecord(STORES.MUTATION, fullRecord)
}

export async function readPendingMutations() {
  const db = await getDatabase()
  return db.getAll(STORES.MUTATION)
}

export function processPendingMutations(): Promise<void> {
  return processOfflineQueues()
}

// Bootstrap, sync and message events can overlap in the same worker. Queue each
// trigger so a later one also sees records added during the previous flush.
let pendingQueueProcessing: Promise<void> = Promise.resolve()

export function processOfflineQueues(): Promise<void> {
  const next = pendingQueueProcessing.then(flushOfflineQueues, flushOfflineQueues)
  pendingQueueProcessing = next
  return next
}

/** Web Locks name shared by every worker instance so only one replay pass runs at a time. */
const REPLAY_LOCK_NAME = "ecosystem-offline-queue-replay"
const REPLAY_STORES = [STORES.NAVIGATION, STORES.REPORT, STORES.MUTATION] as const

type ReplayStore = (typeof REPLAY_STORES)[number]
type ReplayDatabase = Awaited<ReturnType<typeof getDatabase>>

/** Fields shared by every queued record. A navigation record carries no request. */
interface QueuedRecord {
  id: number
  url: string
  reportUrl?: string
  method: string
  payload?: unknown
  idempotencyKey?: string
  mutationId?: string
  dedupeKey?: string
  timestamp: number
  sessionNonce?: string | null
  retryCount?: number
  nextAttemptAt?: number
}

type ReplayAttempt =
  | { status: "delivered" }
  | { status: "retry"; reason: string }
  | { status: "rejected"; reason: string }

interface ReplayAttemptClaim {
  record: QueuedRecord
  attemptId: string
}

async function flushOfflineQueues() {
  if (!isOnline()) return
  await withReplayLock(replayHeldRecords)
}

/** Ownership loss is permanent for one pass, including after a failed heartbeat. */
interface ReplayOwnership {
  owner: string
  lost: boolean
  isHeld: () => Promise<boolean>
}

type ReplayTask = (db: ReplayDatabase, ownership: ReplayOwnership) => Promise<void>

/** Opens one connection for a pass and closes it once the pass settles. */
async function withOpenDatabase<T>(run: (db: ReplayDatabase) => Promise<T>): Promise<T> {
  const db = await getDatabase()
  try {
    return await run(db)
  } finally {
    db.close()
  }
}

/**
 * Every pass takes the same IndexedDB lease, even when another context lacks Web Locks.
 * The optional native lock is always acquired first; fallback passes never wait for it.
 */
function withReplayLock(task: ReplayTask): Promise<void> {
  const locks: LockManager | undefined = self.navigator.locks
  return locks
    ? locks.request(REPLAY_LOCK_NAME, { mode: "exclusive" }, () => withReplayLease(task))
    : withReplayLease(task)
}

/**
 * Runs a pass while holding the IndexedDB replay lease. The lease is renewed while the pass
 * runs, so a healthy holder keeps it. A worker that stopped renewing (for example a terminated
 * one) loses it after the TTL and another worker can take over. A durable, bounded attempt marker
 * prevents takeover from dispatching another request while the prior request window remains live.
 * Queue fencing and stable idempotency keys still cannot prove a remote side effect happened once.
 */
function withReplayLease(task: ReplayTask): Promise<void> {
  return withOpenDatabase(async (db) => {
    const owner = crypto.randomUUID()
    while (!(await claimReplayLease(db, owner, Date.now))) {
      await new Promise((resolve) => setTimeout(resolve, REPLAY_LEASE_POLL_MS))
    }
    const ownership: ReplayOwnership = {
      owner,
      lost: false,
      async isHeld() {
        if (ownership.lost) return false
        if (!(await renewReplayLease(db, owner, Date.now))) ownership.lost = true
        return !ownership.lost
      },
    }
    const renewal = setInterval(() => void ownership.isHeld(), REPLAY_LEASE_RENEW_MS)
    try {
      await task(db, ownership)
    } finally {
      clearInterval(renewal)
      await releaseReplayLease(db, owner)
    }
  })
}

/**
 * Replays only the records bound to the session that a live window vouches for. Records
 * without a session binding, and records bound to any other session, are never sent.
 */
async function replayHeldRecords(db: ReplayDatabase, ownership: ReplayOwnership): Promise<void> {
  const credentials = await requestReplayCredentials()
  if (!credentials) return
  const passSessionNonce = credentials.sessionNonce
  const now = Date.now()
  for (const store of REPLAY_STORES) {
    const records = (await db.getAll(store)) as QueuedRecord[]
    for (const record of records) {
      if ((await replayRecord(db, store, record, passSessionNonce, now, ownership)) === "stop") {
        return
      }
    }
  }
}

async function replayRecord(
  db: ReplayDatabase,
  store: ReplayStore,
  record: QueuedRecord,
  passSessionNonce: string,
  now: number,
  ownership: ReplayOwnership
): Promise<"stop" | undefined> {
  // An unbound record has no proven owner, so no window can release it.
  if (!record.sessionNonce) return
  if (record.sessionNonce !== passSessionNonce) {
    if (isExpiredOtherSessionRecord(record.timestamp, now)) {
      const outcome = await commitReplayRecord(db, store, record, ownership, { kind: "delete" })
      if (outcome === "stop") return "stop"
      if (outcome === "committed") {
        warn("Dropped expired offline record from another browser session", {
          store,
          id: record.id,
        })
      }
    }
    return
  }

  const target = replayTarget(store, record)
  // A navigation has no request to replay, so it stays queued until a window consumes it.
  if (!target || (record.nextAttemptAt ?? 0) > now) return

  // Wait for another worker's bounded request window before asking a page for credentials.
  // Credential requests happen once the slot is clear, not on every short lease poll.
  let dispatch: { claim: ReplayAttemptClaim; csrfToken: string } | undefined
  while (!dispatch) {
    const ready = await replayAttemptSlotReady(db, store, record, ownership)
    if (ready === "stop") return "stop"
    if (ready === "wait") {
      await new Promise((resolve) => setTimeout(resolve, REPLAY_LEASE_POLL_MS))
      continue
    }
    if (!ready) return

    const credentials = await requestReplayCredentials()
    if (!credentials || credentials.sessionNonce !== passSessionNonce) return "stop"
    // Credential collection can yield to a takeover or a row rewrite. The write claim below
    // revalidates lease, marker and row together immediately before dispatch.
    if (!(await ownership.isHeld())) return "stop"
    const next = await claimReplayAttempt(db, store, record, ownership)
    if (next === "stop") return "stop"
    if (next === "wait") continue
    if (!next) return
    dispatch = { claim: next, csrfToken: credentials.csrfToken }
  }
  record = dispatch.claim.record

  const attempt = await deliver(target, record, dispatch.csrfToken)
  if (attempt.status === "delivered") {
    const outcome = await commitReplayRecord(
      db,
      store,
      record,
      ownership,
      { kind: "delete" },
      dispatch.claim.attemptId
    )
    return outcome === "stop" ? "stop" : undefined
  }
  if (attempt.status === "retry") {
    const retryCount = (record.retryCount ?? 0) + 1
    if (retryCount < REPLAY_MAX_ATTEMPTS) {
      const outcome = await commitReplayRecord(
        db,
        store,
        record,
        ownership,
        {
          kind: "retry",
          retryCount,
          nextAttemptAt: Math.max(now, Date.now()) + replayBackoffMs(retryCount),
        },
        dispatch.claim.attemptId
      )
      return outcome === "stop" ? "stop" : undefined
    }
    return deadLetter(
      db,
      store,
      record,
      ownership,
      `retries-exhausted:${attempt.reason}`,
      dispatch.claim.attemptId
    )
  }
  return deadLetter(db, store, record, ownership, attempt.reason, dispatch.claim.attemptId)
}

type ReplayMutation =
  { kind: "delete" } | { kind: "retry"; retryCount: number; nextAttemptAt: number }

/** A successor's identity/retry state must never be overwritten by an old snapshot. */
const REPLAY_RECORD_METADATA = [
  "id",
  "url",
  "reportUrl",
  "method",
  "idempotencyKey",
  "mutationId",
  "dedupeKey",
  "timestamp",
  "sessionNonce",
  "retryCount",
  "nextAttemptAt",
] as const

/** Readiness check before asking a window for fresh CSRF/session credentials. */
async function replayAttemptSlotReady(
  db: ReplayDatabase,
  store: ReplayStore,
  snapshot: QueuedRecord,
  ownership: ReplayOwnership
): Promise<QueuedRecord | "stop" | "wait" | undefined> {
  const tx = db.transaction([REPLAY_LEASE_STORE, store], "readonly")
  try {
    const leases = tx.objectStore(REPLAY_LEASE_STORE)
    const leaseRequest = leases.get(REPLAY_LEASE_KEY)
    const attemptRequest = leases.get(REPLAY_ACTIVE_ATTEMPT_KEY)
    const currentRequest = tx.objectStore(store).get(snapshot.id)
    const [lease, active, current] = (await Promise.all([
      leaseRequest,
      attemptRequest,
      currentRequest,
    ])) as [
      ReplayLeaseRecord | undefined,
      ReplayActiveAttemptRecord | undefined,
      QueuedRecord | undefined,
    ]
    const timestamp = Date.now()
    if (ownership.lost || lease?.owner !== ownership.owner || lease.expiresAt <= timestamp) {
      ownership.lost = true
      await tx.done
      return "stop"
    }
    if (active && active.expiresAt > timestamp) {
      await tx.done
      return "wait"
    }
    if (!current || REPLAY_RECORD_METADATA.some((key) => current[key] !== snapshot[key])) {
      await tx.done
      return
    }
    await tx.done
    return current
  } catch (error) {
    await tx.done.catch(() => undefined)
    throw error
  }
}

/**
 * Atomically reserves the one network-attempt slot after checking the live lease and row.
 * It returns the current payload after credential renewal while fencing identity, session and
 * retry metadata against the original snapshot. The marker is independent of queue rows.
 */
async function claimReplayAttempt(
  db: ReplayDatabase,
  store: ReplayStore,
  snapshot: QueuedRecord,
  ownership: ReplayOwnership
): Promise<ReplayAttemptClaim | "stop" | "wait" | undefined> {
  const tx = db.transaction([REPLAY_LEASE_STORE, store], "readwrite")
  const leases = tx.objectStore(REPLAY_LEASE_STORE)
  try {
    const leaseRequest = leases.get(REPLAY_LEASE_KEY)
    const attemptRequest = leases.get(REPLAY_ACTIVE_ATTEMPT_KEY)
    const currentRequest = tx.objectStore(store).get(snapshot.id)
    const [lease, active, current] = (await Promise.all([
      leaseRequest,
      attemptRequest,
      currentRequest,
    ])) as [
      ReplayLeaseRecord | undefined,
      ReplayActiveAttemptRecord | undefined,
      QueuedRecord | undefined,
    ]
    const timestamp = Date.now()
    if (ownership.lost || lease?.owner !== ownership.owner || lease.expiresAt <= timestamp) {
      ownership.lost = true
      await tx.done
      return "stop"
    }
    // A request from an expired owner may still be pending. Do not dispatch anything until its
    // bounded request window has elapsed or that exact attempt releases the marker on settlement.
    if (active && active.expiresAt > timestamp) {
      await tx.done
      return "wait"
    }
    if (!current || REPLAY_RECORD_METADATA.some((key) => current[key] !== snapshot[key])) {
      await tx.done
      return
    }

    const attemptId = crypto.randomUUID()
    await leases.put({
      id: REPLAY_ACTIVE_ATTEMPT_KEY,
      owner: ownership.owner,
      attemptId,
      // The owner lease covers the dispatch window; the extra timeout permits recovery after a
      // crashed worker's lease expires, without treating an in-flight request as abandoned early.
      expiresAt: lease.expiresAt + REPLAY_REQUEST_TIMEOUT_MS,
    } satisfies ReplayActiveAttemptRecord)
    await tx.done
    return { record: current, attemptId }
  } catch (error) {
    await tx.done.catch(() => undefined)
    throw error
  }
}

/** Marks a payload that cannot be serialized. Such a row is never sent, so the marker is stable. */
const UNSERIALIZABLE_BODY = Symbol("unserializable-body")

/**
 * The request body that replay sends for a row, or a marker when it cannot be serialized. A commit
 * compares this, the only way replay reads a payload, so a rewrite that changes the bytes sent is
 * detected while a rewrite that sends nothing different (for example a GET) is not.
 */
function replayBodyFingerprint(
  record: QueuedRecord
): string | undefined | typeof UNSERIALIZABLE_BODY {
  try {
    return replayBody(record)
  } catch {
    return UNSERIALIZABLE_BODY
  }
}

/**
 * Lease authorization and the row mutation share one transaction. Only IDB requests are
 * awaited inside it; credentials, network delivery and notifications stay outside.
 * A row whose identity, retry state or request body no longer matches the sent snapshot is left
 * in place for the next pass, and only a lost lease stops the pass.
 */
async function commitReplayRecord(
  db: ReplayDatabase,
  store: ReplayStore,
  record: QueuedRecord,
  ownership: ReplayOwnership,
  mutation: ReplayMutation,
  attemptId?: string
): Promise<"committed" | "missing" | "changed" | "stop"> {
  const tx = db.transaction([REPLAY_LEASE_STORE, store], "readwrite")
  try {
    const leases = tx.objectStore(REPLAY_LEASE_STORE)
    const leaseRequest = leases.get(REPLAY_LEASE_KEY)
    const activeRequest = attemptId ? leases.get(REPLAY_ACTIVE_ATTEMPT_KEY) : undefined
    const queue = tx.objectStore(store)
    const currentRequest = queue.get(record.id)
    const [lease, active, current] = (await Promise.all([
      leaseRequest,
      activeRequest,
      currentRequest,
    ])) as [
      ReplayLeaseRecord | undefined,
      ReplayActiveAttemptRecord | undefined,
      QueuedRecord | undefined,
    ]
    const ownsAttempt =
      !attemptId || (active?.owner === ownership.owner && active.attemptId === attemptId)
    if (attemptId && ownsAttempt) await leases.delete(REPLAY_ACTIVE_ATTEMPT_KEY)
    if (ownership.lost || lease?.owner !== ownership.owner || lease.expiresAt <= Date.now()) {
      ownership.lost = true
      await tx.done
      return "stop"
    }
    if (!ownsAttempt) {
      await tx.done
      return "stop"
    }
    if (!current) {
      await tx.done
      return "missing"
    }
    if (
      REPLAY_RECORD_METADATA.some((key) => current[key] !== record[key]) ||
      replayBodyFingerprint(current) !== replayBodyFingerprint(record)
    ) {
      await tx.done
      return "changed"
    }
    if (mutation.kind === "delete") {
      await queue.delete(record.id)
    } else {
      await queue.put({
        ...current,
        retryCount: mutation.retryCount,
        nextAttemptAt: mutation.nextAttemptAt,
      })
    }
    await tx.done
    return "committed"
  } catch (error) {
    await tx.done.catch(() => undefined)
    throw error
  }
}

async function deadLetter(
  db: ReplayDatabase,
  store: ReplayStore,
  record: QueuedRecord,
  ownership: ReplayOwnership,
  reason: string,
  attemptId?: string
): Promise<"stop" | undefined> {
  const outcome = await commitReplayRecord(
    db,
    store,
    record,
    ownership,
    { kind: "delete" },
    attemptId
  )
  if (outcome === "stop") return "stop"
  if (outcome !== "committed") return
  warn("Dead-lettered offline record", { store, id: record.id, reason })
  // Visibility only: the notice names the queue and the reason, never the URL, payload or account.
  await broadcastMessage({ type: OFFLINE_DEAD_LETTER_MESSAGE_TYPE, store, reason }).catch(
    () => undefined
  )
}

function replayTarget(store: ReplayStore, record: QueuedRecord): string | undefined {
  if (store === STORES.REPORT) return record.reportUrl
  if (store === STORES.MUTATION) return record.url
  return undefined
}

async function deliver(
  url: string,
  record: QueuedRecord,
  csrfToken: string
): Promise<ReplayAttempt> {
  const target = sameOriginHref(url)
  if (!target) return { status: "rejected", reason: "cross-origin" }

  let body: string | undefined
  try {
    body = replayBody(record)
  } catch {
    return { status: "rejected", reason: "unserializable" }
  }

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), REPLAY_REQUEST_TIMEOUT_MS)
  try {
    const response = await fetch(target, {
      method: record.method,
      headers: replayHeaders(record, csrfToken, body !== undefined),
      body,
      // A redirect, for example to a login page, must never look like a delivered write.
      redirect: "manual",
      signal: controller.signal,
    })
    if (response.ok) return { status: "delivered" }
    const reason = `status-${response.status}`
    return isRetryableReplayStatus(response.status)
      ? { status: "retry", reason }
      : { status: "rejected", reason }
  } catch {
    return { status: "retry", reason: "network" }
  } finally {
    clearTimeout(timer)
  }
}

/** Resolves a replay target and refuses anything outside this worker's origin. */
function sameOriginHref(value: string): string | null {
  try {
    const url = new URL(value, self.location.origin)
    return url.origin === self.location.origin ? url.href : null
  } catch {
    return null
  }
}

function replayBody(record: QueuedRecord): string | undefined {
  if (record.payload === undefined || record.method === "GET" || record.method === "HEAD") {
    return undefined
  }
  return JSON.stringify(record.payload)
}

function replayHeaders(
  record: QueuedRecord,
  csrfToken: string,
  hasBody: boolean
): Record<string, string> {
  return {
    Accept: "application/json",
    "X-CSRF-Token": csrfToken,
    ...(hasBody ? { "Content-Type": "application/json" } : {}),
    ...(record.idempotencyKey ? { "Idempotency-Key": record.idempotencyKey } : {}),
  }
}

export function processPendingNavigations(): Promise<void> {
  return processOfflineQueues()
}

export function processPendingReports(): Promise<void> {
  return processOfflineQueues()
}
