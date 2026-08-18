/// <reference lib="webworker" />
declare const self: ServiceWorkerGlobalScope

import { openDB, type IDBPDatabase } from "idb"
import { log, warn } from "./logger"

const CLICK_DB_NAME = "notification-interactions"
const DB_VERSION = 4

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

export async function storePendingNavigation(record: { url: string; timestamp: number }) {
  return addRecord(STORES.NAVIGATION, record)
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
}) {
  const method = (record.method ?? "POST").toUpperCase()
  const idempotentMethods = ["GET", "PUT", "DELETE", "HEAD"]

  if (idempotentMethods.includes(method)) {
    // DEBT-04 (audit Wave 11): deduplicate idempotent requests by a framed
    // method+URL+body tuple so different methods and field boundaries cannot collide.
    // A user going offline then back online while the same resource is pending
    // should not enqueue duplicate requests that create duplicate side-effects.
    const dedupeKey = await digestKey(
      JSON.stringify([method, record.reportUrl, record.payload ?? null])
    )
    const db = await getDatabase()
    const existing = await db.getAllFromIndex(STORES.REPORT, "dedupeKey", dedupeKey)
    if (existing.length > 0) {
      return // already queued — skip
    }
    return db.add(STORES.REPORT, { ...record, method, dedupeKey })
  }

  // POST (and other non-idempotent): always enqueue; attach a random idempotency
  // key so the server can deduplicate retries on its side (via Idempotency-Key header).
  const idempotencyKey = crypto.randomUUID()
  return addRecord(STORES.REPORT, { ...record, method, idempotencyKey })
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
  }
  return addRecord(STORES.MUTATION, fullRecord)
}

export async function readPendingMutations() {
  const db = await getDatabase()
  return db.getAll(STORES.MUTATION)
}

export async function processPendingMutations() {
  if (!isOnline()) return
  const db = await getDatabase()
  type PersistedPendingMutationRecord = PendingMutationRecord & { id: number }
  const records = (await db.getAll(STORES.MUTATION)) as PersistedPendingMutationRecord[]
  if (!records || !records.length) return

  records.sort((a, b) => a.timestamp - b.timestamp)

  const broadcast =
    typeof BroadcastChannel !== "undefined"
      ? new BroadcastChannel("offline-mutation-sync-channel")
      : null
  const notifyBroadcast = (msg: unknown) => {
    if (broadcast && typeof broadcast.postMessage === "function") {
      try {
        broadcast.postMessage(msg)
      } catch {
        /* ignore */
      }
    }
  }

  try {
    for (const record of records) {
      if (record.retryCount >= 5) {
        warn("Mutation exceeded max retries, discarding:", record)
        await db.delete(STORES.MUTATION, record.id)
        notifyBroadcast({ type: "MUTATION_FAILED_PERMANENT", record })
        continue
      }

      try {
        const response = await fetch(record.url, {
          method: record.method,
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": record.idempotencyKey,
            ...(record.headers ?? {}),
          },
          body: record.payload ? JSON.stringify(record.payload) : undefined,
          signal: AbortSignal.timeout(10_000),
        })

        if (response.ok) {
          await db.delete(STORES.MUTATION, record.id)
          notifyBroadcast({ type: "MUTATION_SYNCED", record })
        } else if (response.status >= 400 && response.status < 500 && response.status !== 429) {
          warn(`Mutation returned non-retriable status ${response.status}:`, record)
          await db.delete(STORES.MUTATION, record.id)
          notifyBroadcast({ type: "MUTATION_REJECTED", record, status: response.status })
        } else {
          record.retryCount += 1
          await db.put(STORES.MUTATION, record)
        }
      } catch (_err) {
        record.retryCount += 1
        await db.put(STORES.MUTATION, record)
      }
    }
  } finally {
    broadcast?.close()
  }
}

export async function processOfflineQueues() {
  if (!isOnline()) return

  log("Processing offline queues...")
  const db = await getDatabase()

  await Promise.all([
    processPendingNavigations(),
    processPendingReports(),
    processNewsInteractionQueue(db),
    processPendingMutations(),
  ])
}

export async function processPendingNavigations() {
  if (!isOnline()) return
  const db = await getDatabase()
  const records = await db.getAll(STORES.NAVIGATION)
  for (const record of records) {
    log("Processing navigation", record)
    if (self.clients && typeof self.clients.openWindow === "function") {
      await self.clients.openWindow(record.url).catch(() => {})
    }
    await db.delete(STORES.NAVIGATION, record.id)
  }
}

// RZ-NEW-06 + TD-NEW-06 (audit 2026-03): Replaced sequential for-loop (which
// aborted remaining records on first failure) with Promise.allSettled so that
// all reports are attempted in parallel. AbortSignal.timeout(10_000) prevents
// a single slow endpoint from stalling the entire flush.
export async function processPendingReports() {
  if (!isOnline()) return
  const db = await getDatabase()
  const records = await db.getAll(STORES.REPORT)

  const results = await Promise.allSettled(
    records.map(async (record) => {
      const headers: Record<string, string> = { "Content-Type": "application/json" }
      // DEBT-04: forward idempotency key so the server can deduplicate retries
      if (record.idempotencyKey) {
        headers["Idempotency-Key"] = record.idempotencyKey
      }
      const method = (record.method ?? "POST").toUpperCase()
      const response = await fetch(record.reportUrl, {
        method,
        ...(method !== "GET" && method !== "HEAD" ? { body: JSON.stringify(record.payload) } : {}),
        headers,
        keepalive: true,
        signal: AbortSignal.timeout(10_000),
      })
      if (response.ok) {
        await db.delete(STORES.REPORT, record.id)
      }
    })
  )

  results
    .filter((r): r is PromiseRejectedResult => r.status === "rejected")
    .forEach((r) => warn("Failed to sync report", r.reason))
}

// PERF-03 (audit 2026-03-06): process all queued interactions concurrently instead
// of sequentially. The old for-loop stalled on first network failure (break) and
// kept all subsequent records un-synced for the entire offline period.
// Promise.allSettled fires every fetch in parallel and collects outcomes without
// short-circuiting — a single timeout does not block the rest of the queue.
async function processNewsInteractionQueue(db: IDBPDatabase) {
  const records = await db.getAll(STORES.NEWS_INTERACTION)

  const results = await Promise.allSettled(
    records.map(async (record) => {
      const { url, method = "POST", payload } = record
      const options: RequestInit = {
        method,
        headers: { "Content-Type": "application/json" },
        ...(method !== "GET" && method !== "HEAD" ? { body: JSON.stringify(payload) } : {}),
      }

      const response = await fetch(url, options)
      if (response.ok || response.status === 400 || response.status === 404) {
        // Drop records that succeeded or can never succeed (client errors)
        await db.delete(STORES.NEWS_INTERACTION, record.id)
      }
    })
  )

  // Log failures without breaking the loop
  results
    .filter((r): r is PromiseRejectedResult => r.status === "rejected")
    .forEach((r) => warn("Failed to sync news interaction", r.reason))
}
