/// <reference lib="webworker" />
declare const self: ServiceWorkerGlobalScope

import { openDB } from "idb"
import { warn } from "./logger"
import {
  NOTIFICATION_INTERACTIONS_DB_NAME as CLICK_DB_NAME,
  NOTIFICATION_INTERACTIONS_DB_VERSION as DB_VERSION,
} from "../constants/notificationInteractionsDb"
import { requestReplayCredentials } from "./replayCredentials"
import {
  isExpiredOtherSessionRecord,
  isRetryableReplayStatus,
  REPLAY_MAX_ATTEMPTS,
  REPLAY_REQUEST_TIMEOUT_MS,
  replayBackoffMs,
} from "./replayPolicy"

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
  return openDB(CLICK_DB_NAME, DB_VERSION, {
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
        // implicit upgrade transaction is valid here. Because DB_VERSION is 4,
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
    },
  })
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
  timestamp: number
  sessionNonce?: string | null
  retryCount?: number
  nextAttemptAt?: number
}

type ReplayAttempt =
  | { status: "delivered" }
  | { status: "retry"; reason: string }
  | { status: "rejected"; reason: string }

async function flushOfflineQueues() {
  if (!isOnline()) return
  await withReplayLock(replayHeldRecords)
}

/** Serializes passes across worker instances. Without Web Locks the in-process chain still applies. */
function withReplayLock(task: () => Promise<void>): Promise<void> {
  const locks: LockManager | undefined = self.navigator.locks
  return locks ? locks.request(REPLAY_LOCK_NAME, { mode: "exclusive" }, task) : task()
}

/**
 * Replays only the records bound to the session that a live window vouches for. Records
 * without a session binding, and records bound to any other session, are never sent.
 */
async function replayHeldRecords(): Promise<void> {
  const db = await getDatabase()
  try {
    const credentials = await requestReplayCredentials()
    if (!credentials) return
    const passSessionNonce = credentials.sessionNonce
    const now = Date.now()
    for (const store of REPLAY_STORES) {
      const records = (await db.getAll(store)) as QueuedRecord[]
      for (const record of records) {
        if ((await replayRecord(db, store, record, passSessionNonce, now)) === "stop") return
      }
    }
  } finally {
    db.close()
  }
}

async function replayRecord(
  db: ReplayDatabase,
  store: ReplayStore,
  record: QueuedRecord,
  passSessionNonce: string,
  now: number
): Promise<"stop" | undefined> {
  // An unbound record has no proven owner, so no window can release it.
  if (!record.sessionNonce) return
  if (record.sessionNonce !== passSessionNonce) {
    if (isExpiredOtherSessionRecord(record.timestamp, now)) {
      await db.delete(store, record.id)
      warn("Dropped expired offline record from another browser session", { store, id: record.id })
    }
    return
  }

  const target = replayTarget(store, record)
  // A navigation has no request to replay, so it stays queued until a window consumes it.
  if (!target || (record.nextAttemptAt ?? 0) > now) return

  // Recheck only send-eligible rows, without adopting another session during this pass.
  const credentials = await requestReplayCredentials()
  if (!credentials || credentials.sessionNonce !== passSessionNonce) return "stop"

  const attempt = await deliver(target, record, credentials.csrfToken)
  if (attempt.status === "delivered") {
    await db.delete(store, record.id)
    return
  }
  if (attempt.status === "retry") {
    const retryCount = (record.retryCount ?? 0) + 1
    if (retryCount < REPLAY_MAX_ATTEMPTS) {
      await db.put(store, {
        ...record,
        retryCount,
        nextAttemptAt: now + replayBackoffMs(retryCount),
      })
      return
    }
    await deadLetter(db, store, record.id, `retries-exhausted:${attempt.reason}`)
    return
  }
  await deadLetter(db, store, record.id, attempt.reason)
}

async function deadLetter(
  db: ReplayDatabase,
  store: ReplayStore,
  id: number,
  reason: string
): Promise<void> {
  await db.delete(store, id)
  warn("Dead-lettered offline record", { store, id, reason })
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
