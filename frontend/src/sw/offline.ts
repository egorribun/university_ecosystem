/// <reference lib="webworker" />
declare const self: ServiceWorkerGlobalScope

import { openDB } from "idb"
import { log } from "./logger"
import {
  NOTIFICATION_INTERACTIONS_DB_NAME as CLICK_DB_NAME,
  NOTIFICATION_INTERACTIONS_DB_VERSION as DB_VERSION,
} from "../constants/notificationInteractionsDb"

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

async function flushOfflineQueues() {
  if (!isOnline()) return

  // The legacy stores do not identify their originating session. A worker can
  // wake after another account signs in, so keep every record untouched until
  // a session-bound, CSRF-safe replay protocol is available.
  log("Legacy offline queues are held pending safe replay")
  await getDatabase()
}

export function processPendingNavigations(): Promise<void> {
  return processOfflineQueues()
}

export function processPendingReports(): Promise<void> {
  return processOfflineQueues()
}
