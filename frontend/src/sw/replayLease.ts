import type { IDBPDatabase } from "idb"
import { REPLAY_LEASE_TTL_MS, REPLAY_REQUEST_TIMEOUT_MS } from "./replayPolicy"

/** Object store holding the replay lease and its single in-flight attempt marker. */
export const REPLAY_LEASE_STORE = "replay-lease"
export const REPLAY_LEASE_KEY = "replay"
/** Single durable marker for the one HTTP replay request that may be in flight. */
export const REPLAY_ACTIVE_ATTEMPT_KEY = "active-attempt"

export interface ReplayLeaseRecord {
  id: typeof REPLAY_LEASE_KEY
  owner: string
  expiresAt: number
}

export interface ReplayActiveAttemptRecord {
  id: typeof REPLAY_ACTIVE_ATTEMPT_KEY
  owner: string
  attemptId: string
  expiresAt: number
}

/**
 * Takes the lease when it is free, expired, or already held by `owner`, which also renews
 * it. The check and the write share one readwrite transaction, so two workers cannot both
 * succeed: IndexedDB serializes overlapping transactions across every connection.
 */
export async function claimReplayLease(
  db: IDBPDatabase,
  owner: string,
  now: number | (() => number)
): Promise<boolean> {
  const tx = db.transaction(REPLAY_LEASE_STORE, "readwrite")
  const current = (await tx.store.get(REPLAY_LEASE_KEY)) as ReplayLeaseRecord | undefined
  const timestamp = typeof now === "function" ? now() : now
  if (current && current.owner !== owner && current.expiresAt > timestamp) {
    await tx.done
    return false
  }
  await tx.store.put({ id: REPLAY_LEASE_KEY, owner, expiresAt: timestamp + REPLAY_LEASE_TTL_MS })
  await tx.done
  return true
}

/**
 * Renews a lease the pass already holds and keeps its attempt marker live through the request
 * timeout window. A failed renewal, including a closed connection, reports false so the pass stops.
 */
export async function renewReplayLease(
  db: IDBPDatabase,
  owner: string,
  now: number | (() => number)
): Promise<boolean> {
  try {
    const tx = db.transaction(REPLAY_LEASE_STORE, "readwrite")
    const [current, active] = (await Promise.all([
      tx.store.get(REPLAY_LEASE_KEY),
      tx.store.get(REPLAY_ACTIVE_ATTEMPT_KEY),
    ])) as [ReplayLeaseRecord | undefined, ReplayActiveAttemptRecord | undefined]
    const timestamp = typeof now === "function" ? now() : now
    if (!current || current.owner !== owner || current.expiresAt <= timestamp) {
      await tx.done
      return false
    }
    const expiresAt = timestamp + REPLAY_LEASE_TTL_MS
    await tx.store.put({ ...current, expiresAt })
    if (active?.owner === owner) {
      await tx.store.put({
        ...active,
        expiresAt: expiresAt + REPLAY_REQUEST_TIMEOUT_MS,
      })
    }
    await tx.done
    return true
  } catch {
    return false
  }
}

/**
 * Deletes the lease only while `owner` still holds it. A lease that was taken over belongs to
 * another worker, and a failed release simply expires on its own.
 */
export async function releaseReplayLease(db: IDBPDatabase, owner: string): Promise<void> {
  try {
    const tx = db.transaction(REPLAY_LEASE_STORE, "readwrite")
    const current = (await tx.store.get(REPLAY_LEASE_KEY)) as ReplayLeaseRecord | undefined
    if (current?.owner === owner) await tx.store.delete(REPLAY_LEASE_KEY)
    await tx.done
  } catch {
    // The lease expires after REPLAY_LEASE_TTL_MS, so a failed release cannot wedge the queue.
  }
}
