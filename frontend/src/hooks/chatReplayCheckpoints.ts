/**
 * Durable per-user chat replay checkpoints.
 *
 * Each authenticated user owns an LRU registry of chat id → last accepted
 * stream sequence and opaque resume token. Registries live in process memory
 * (bounded to the most recently used users) and are mirrored to
 * sessionStorage so a reload can resume every room without replaying it.
 */

export type ReplayCheckpoint = { sequence: number; resumeToken: string }

const REPLAY_CHECKPOINT_PREFIX = "university.chat.replay.v2:"
export const REPLAY_CHECKPOINT_LIMIT = 256
export const REPLAY_CHECKPOINT_USER_LIMIT = 16
export const REPLAY_CHECKPOINT_STORAGE_LIMIT = 65_536
const CHAT_ID_MAX_LENGTH = 512
const RESUME_TOKEN_MAX_LENGTH = 4096

type StoredCheckpoint = [chatId: string, sequence: number, resumeToken: string]

// Keyed like the mount counts; an anonymous (undefined) user never gets a registry.
const replayCheckpointMemory = new Map<string | undefined, Map<string, ReplayCheckpoint>>()
const replayCheckpointMounts = new Map<string | undefined, number>()

export function replayCheckpointKey(userId: string): string {
  return `${REPLAY_CHECKPOINT_PREFIX}${encodeURIComponent(userId)}`
}

function persistReplayCheckpoints(userId: string, registry: Map<string, ReplayCheckpoint>): void {
  try {
    window.sessionStorage.setItem(
      replayCheckpointKey(userId),
      JSON.stringify({
        entries: [...registry.entries()].map(([chatId, checkpoint]) => [
          chatId,
          checkpoint.sequence,
          checkpoint.resumeToken,
        ]),
      })
    )
  } catch {
    // The in-memory registry still protects this mounted browser session.
  }
}

function isStoredCheckpoint(entry: unknown): entry is StoredCheckpoint {
  return (
    Array.isArray(entry) &&
    entry.length === 3 &&
    typeof entry[0] === "string" &&
    entry[0].length > 0 &&
    entry[0].length <= CHAT_ID_MAX_LENGTH &&
    Number.isSafeInteger(entry[1]) &&
    entry[1] >= 1 &&
    typeof entry[2] === "string" &&
    entry[2].length > 0 &&
    entry[2].length <= RESUME_TOKEN_MAX_LENGTH
  )
}

/** The newest stored entries, or null when the stored registry is not valid. */
function parseStoredCheckpoints(stored: string): StoredCheckpoint[] | null {
  if (stored.length > REPLAY_CHECKPOINT_STORAGE_LIMIT) return null
  const { entries } = JSON.parse(stored) as { entries?: unknown }
  if (!Array.isArray(entries)) return null
  const recent = entries.slice(-REPLAY_CHECKPOINT_LIMIT)
  return recent.every(isStoredCheckpoint) ? recent : null
}

function loadReplayCheckpoints(userId: string): Map<string, ReplayCheckpoint> {
  const registry = new Map<string, ReplayCheckpoint>()
  const key = replayCheckpointKey(userId)
  try {
    const stored = window.sessionStorage.getItem(key)
    if (stored === null) return registry
    const entries = parseStoredCheckpoints(stored)
    if (entries !== null) {
      for (const [chatId, sequence, resumeToken] of entries) {
        // A repeated chat id keeps the recency of its last occurrence.
        registry.delete(chatId)
        registry.set(chatId, { sequence, resumeToken })
      }
      return registry
    }
  } catch {
    // Unreadable storage or malformed JSON is discarded below.
  }
  try {
    window.sessionStorage.removeItem(key)
  } catch {
    // Storage can be disabled; the empty registry is already fail-closed.
  }
  return registry
}

function replayCheckpointRegistry(userId: string): Map<string, ReplayCheckpoint> {
  const cached = replayCheckpointMemory.get(userId)
  if (cached) {
    replayCheckpointMemory.delete(userId)
    replayCheckpointMemory.set(userId, cached)
    return cached
  }

  const registry = loadReplayCheckpoints(userId)
  replayCheckpointMemory.set(userId, registry)
  // Registries are added one at a time, so at most one user is over the limit.
  if (replayCheckpointMemory.size > REPLAY_CHECKPOINT_USER_LIMIT) {
    replayCheckpointMemory.delete(replayCheckpointMemory.keys().next().value!)
  }
  return registry
}

/** Read a room checkpoint and mark it as the most recently used one. */
export function readAndTouchReplayCheckpoint(
  userId: string | undefined,
  chatId: string
): ReplayCheckpoint | undefined {
  if (!userId) return undefined
  const registry = replayCheckpointRegistry(userId)
  const checkpoint = registry.get(chatId)
  if (checkpoint === undefined) return undefined
  registry.delete(chatId)
  registry.set(chatId, checkpoint)
  persistReplayCheckpoints(userId, registry)
  return checkpoint
}

/** Read a room checkpoint without changing its recency. */
export function peekReplayCheckpoint(
  userId: string | undefined,
  chatId: string
): ReplayCheckpoint | undefined {
  if (!userId) return undefined
  return replayCheckpointRegistry(userId).get(chatId)
}

export function writeReplayCheckpoint(
  userId: string | undefined,
  chatId: string,
  sequence: number,
  resumeToken: string,
  protectedChatId: string | null
): void {
  if (!userId) return
  const registry = replayCheckpointRegistry(userId)
  registry.delete(chatId)
  registry.set(chatId, { sequence, resumeToken })
  // One entry was added, so at most one is over the limit. The written room
  // is the newest key and the registry holds more than two rooms, so the first
  // key that is not the protected (active) room is never the written one.
  if (registry.size > REPLAY_CHECKPOINT_LIMIT) {
    const evictionCandidate = [...registry.keys()].find(
      (candidate) => candidate !== protectedChatId
    )
    registry.delete(evictionCandidate!)
  }
  persistReplayCheckpoints(userId, registry)
}

export function clearReplayCheckpoints(userId: string | undefined): void {
  if (!userId) return
  replayCheckpointMemory.delete(userId)
  try {
    window.sessionStorage.removeItem(replayCheckpointKey(userId))
  } catch {
    // Storage can be disabled; the in-memory state was already cleared.
  }
}

export function removeReplayCheckpoint(userId: string | undefined, chatId: string): void {
  if (!userId) return
  const registry = replayCheckpointRegistry(userId)
  if (!registry.delete(chatId)) return
  persistReplayCheckpoints(userId, registry)
}

/**
 * Keep a user's in-memory registry while at least one hook instance of that
 * user is mounted; the returned release frees it after the last one unmounts.
 * An anonymous session has no registry, so retaining it has no effect.
 */
export function retainReplayCheckpoints(userId: string | undefined): () => void {
  replayCheckpointMounts.set(userId, (replayCheckpointMounts.get(userId) ?? 0) + 1)
  return () => {
    // Every release follows its own retain above.
    const remaining = replayCheckpointMounts.get(userId)! - 1
    if (remaining > 0) {
      replayCheckpointMounts.set(userId, remaining)
      return
    }
    replayCheckpointMounts.delete(userId)
    replayCheckpointMemory.delete(userId)
  }
}
