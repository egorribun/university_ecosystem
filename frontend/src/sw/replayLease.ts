import type { IDBPDatabase } from "idb"
import { REPLAY_LEASE_TTL_MS } from "./replayPolicy"

/** Object store holding the single replay-lease row. Created by schema version 5. */
export const REPLAY_LEASE_STORE = "replay-lease"
const REPLAY_LEASE_KEY = "replay"

interface ReplayLeaseRecord {
  id: typeof REPLAY_LEASE_KEY
  owner: string
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
  now: number
): Promise<boolean> {
  const tx = db.transaction(REPLAY_LEASE_STORE, "readwrite")
  const current = (await tx.store.get(REPLAY_LEASE_KEY)) as ReplayLeaseRecord | undefined
  if (current && current.owner !== owner && current.expiresAt > now) {
    await tx.done
    return false
  }
  await tx.store.put({ id: REPLAY_LEASE_KEY, owner, expiresAt: now + REPLAY_LEASE_TTL_MS })
  await tx.done
  return true
}

/**
 * Renews a lease the pass already holds. A failed renewal, including a closed connection,
 * reports false so the pass stops before it sends another request.
 */
export async function renewReplayLease(
  db: IDBPDatabase,
  owner: string,
  now: number
): Promise<boolean> {
  try {
    return await claimReplayLease(db, owner, now)
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
