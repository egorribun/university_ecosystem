import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

type CheckpointModule = typeof import("../chatReplayCheckpoints")
let store: CheckpointModule

const USER = "checkpoint-user"
const KEY = `university.chat.replay.v2:${USER}`

const storedEntries = (userId = USER) => {
  const raw = window.sessionStorage.getItem(
    `university.chat.replay.v2:${encodeURIComponent(userId)}`
  )
  return raw === null ? null : (JSON.parse(raw) as { entries: unknown[] }).entries
}
const persist = (entries: unknown, userId = USER) =>
  window.sessionStorage.setItem(
    `university.chat.replay.v2:${encodeURIComponent(userId)}`,
    JSON.stringify({ entries })
  )

beforeEach(async () => {
  // The registry is module state; every test starts from a fresh module.
  vi.resetModules()
  window.sessionStorage.clear()
  store = await import("../chatReplayCheckpoints")
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("loading persisted checkpoints", () => {
  it("loads valid stored checkpoints and leaves storage untouched on a miss", () => {
    const removeItem = vi.spyOn(Storage.prototype, "removeItem")
    persist([["room", 7, "token-7"]])

    expect(store.peekReplayCheckpoint(USER, "room")).toStrictEqual({
      sequence: 7,
      resumeToken: "token-7",
    })
    expect(store.peekReplayCheckpoint("fresh-user", "room")).toBeUndefined()
    expect(removeItem).not.toHaveBeenCalled()
  })

  it("keeps the recency of the last occurrence of a repeated room", () => {
    persist([
      ["a", 1, "t1"],
      ["b", 2, "t2"],
      ["a", 3, "t3"],
    ])

    store.writeReplayCheckpoint(USER, "c", 4, "t4", null)

    expect(storedEntries()).toStrictEqual([
      ["b", 2, "t2"],
      ["a", 3, "t3"],
      ["c", 4, "t4"],
    ])
  })

  it("loads only the newest stored rooms and ignores older invalid entries", () => {
    const entries: unknown[] = [["stale", 0, ""]]
    for (let index = 0; index < store.REPLAY_CHECKPOINT_LIMIT; index += 1) {
      entries.push([`room-${index}`, index + 1, `token-${index}`])
    }
    persist(entries)

    expect(store.peekReplayCheckpoint(USER, "stale")).toBeUndefined()
    expect(store.peekReplayCheckpoint(USER, "room-0")).toStrictEqual({
      sequence: 1,
      resumeToken: "token-0",
    })
  })

  it.each([
    ["exactly the storage limit", storeLimitPayload(0), true],
    ["one character over the storage limit", storeLimitPayload(1), false],
  ])("accepts a stored registry of %s only within the bound", (_label, payload, accepted) => {
    window.sessionStorage.setItem(KEY, payload)

    expect(store.peekReplayCheckpoint(USER, "room") !== undefined).toBe(accepted)
  })

  it.each([
    ["an entry that is not an array", { room: 1 }],
    ["an entry with too few fields", ["room", 1]],
    ["an entry with too many fields", ["room", 1, "token", "extra"]],
    ["a non-string room", [7, 1, "token"]],
    ["an empty room", ["", 1, "token"]],
    ["an overlong room", ["r".repeat(513), 1, "token"]],
    ["a non-numeric sequence", ["room", "1", "token"]],
    ["a fractional sequence", ["room", 1.5, "token"]],
    ["an unsafe sequence", ["room", Number.MAX_SAFE_INTEGER + 1, "token"]],
    ["a zero sequence", ["room", 0, "token"]],
    ["a non-string token", ["room", 1, 7]],
    ["an empty token", ["room", 1, ""]],
    ["an overlong token", ["room", 1, "t".repeat(4097)]],
  ])("discards the whole registry for %s", (_label, entry) => {
    persist([["valid", 1, "token"], entry])

    expect(store.peekReplayCheckpoint(USER, "valid")).toBeUndefined()
    expect(window.sessionStorage.getItem(KEY)).toBeNull()
  })

  it.each([
    ["no entries list", JSON.stringify({})],
    ["a non-object document", "null"],
    ["malformed JSON", "{"],
  ])("discards a stored registry with %s", (_label, raw) => {
    window.sessionStorage.setItem(KEY, raw)

    expect(store.peekReplayCheckpoint(USER, "room")).toBeUndefined()
    expect(window.sessionStorage.getItem(KEY)).toBeNull()
  })

  it("accepts entries exactly at every field bound", () => {
    const room = "r".repeat(512)
    const token = "t".repeat(4096)
    persist([[room, 1, token]])

    expect(store.peekReplayCheckpoint(USER, room)).toStrictEqual({
      sequence: 1,
      resumeToken: token,
    })
  })

  it("fails closed when storage itself is unavailable", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied")
    })
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("denied")
    })

    expect(store.peekReplayCheckpoint(USER, "room")).toBeUndefined()
  })
})

function storeLimitPayload(extra: number): string {
  const base = JSON.stringify({ entries: [["room", 1, "token"]] })
  // Whitespace after the document keeps it valid JSON of an exact length.
  return base + " ".repeat(65_536 - base.length + extra)
}

describe("user registry memory", () => {
  const seed = (count: number) => {
    for (let index = 0; index < count; index += 1) {
      store.writeReplayCheckpoint(`user-${index}`, "room", index + 1, `token-${index}`, null)
    }
  }
  const inMemory = (userId: string) => {
    // Only the in-memory registry can answer once storage is gone.
    return store.peekReplayCheckpoint(userId, "room") !== undefined
  }

  it("keeps exactly the most recent sixteen users in memory", () => {
    seed(16)
    window.sessionStorage.clear()
    expect(inMemory("user-0")).toBe(true)

    store.writeReplayCheckpoint("user-16", "room", 17, "token-16", null)
    window.sessionStorage.clear()
    expect(inMemory("user-1")).toBe(false)
    expect(inMemory("user-16")).toBe(true)
  })

  it("refreshes the recency of a user on every access", () => {
    seed(16)
    store.peekReplayCheckpoint("user-0", "room")
    store.writeReplayCheckpoint("user-16", "room", 17, "token-16", null)
    window.sessionStorage.clear()

    expect(inMemory("user-0")).toBe(true)
    expect(inMemory("user-1")).toBe(false)
  })

  it("keeps a registry while any retained mount of that user remains", () => {
    const releaseFirst = store.retainReplayCheckpoints(USER)
    const releaseSecond = store.retainReplayCheckpoints(USER)
    store.writeReplayCheckpoint(USER, "room", 1, "token", null)
    window.sessionStorage.clear()

    releaseFirst()
    expect(store.peekReplayCheckpoint(USER, "room")).toBeDefined()
    releaseSecond()
    expect(store.peekReplayCheckpoint(USER, "room")).toBeUndefined()
  })

  it("frees the registry again after a later remount of the same user", () => {
    store.retainReplayCheckpoints(USER)()
    const release = store.retainReplayCheckpoints(USER)
    store.writeReplayCheckpoint(USER, "room", 1, "token", null)
    window.sessionStorage.clear()

    release()
    expect(store.peekReplayCheckpoint(USER, "room")).toBeUndefined()
  })

  it("treats retaining an anonymous session as a no-op", () => {
    store.writeReplayCheckpoint(USER, "room", 1, "token", null)
    store.retainReplayCheckpoints(undefined)()

    expect(store.peekReplayCheckpoint(USER, "room")).toBeDefined()
  })
})

describe("room checkpoints", () => {
  it("moves a read room to the most recent position", () => {
    store.writeReplayCheckpoint(USER, "a", 1, "t1", null)
    store.writeReplayCheckpoint(USER, "b", 2, "t2", null)

    expect(store.readAndTouchReplayCheckpoint(USER, "a")).toStrictEqual({
      sequence: 1,
      resumeToken: "t1",
    })
    expect(storedEntries()).toStrictEqual([
      ["b", 2, "t2"],
      ["a", 1, "t1"],
    ])
  })

  it("keeps later writes persisted after reading an unknown room", () => {
    store.writeReplayCheckpoint(USER, "a", 1, "t1", null)

    expect(store.readAndTouchReplayCheckpoint(USER, "missing")).toBeUndefined()
    store.writeReplayCheckpoint(USER, "b", 2, "t2", null)

    expect(storedEntries()).toStrictEqual([
      ["a", 1, "t1"],
      ["b", 2, "t2"],
    ])
  })

  it("does not reorder rooms on a peek", () => {
    store.writeReplayCheckpoint(USER, "a", 1, "t1", null)
    store.writeReplayCheckpoint(USER, "b", 2, "t2", null)
    store.peekReplayCheckpoint(USER, "a")
    store.writeReplayCheckpoint(USER, "c", 3, "t3", null)

    expect(storedEntries()).toStrictEqual([
      ["a", 1, "t1"],
      ["b", 2, "t2"],
      ["c", 3, "t3"],
    ])
  })

  it("moves a rewritten room to the most recent position", () => {
    store.writeReplayCheckpoint(USER, "a", 1, "t1", null)
    store.writeReplayCheckpoint(USER, "b", 2, "t2", null)
    store.writeReplayCheckpoint(USER, "a", 3, "t3", null)

    expect(storedEntries()).toStrictEqual([
      ["b", 2, "t2"],
      ["a", 3, "t3"],
    ])
  })

  it("bounds the rooms of a user and never evicts the protected room", () => {
    for (let index = 0; index < store.REPLAY_CHECKPOINT_LIMIT; index += 1) {
      store.writeReplayCheckpoint(USER, `room-${index}`, index + 1, `t${index}`, "room-0")
    }
    expect(storedEntries()).toHaveLength(store.REPLAY_CHECKPOINT_LIMIT)

    store.writeReplayCheckpoint(USER, "room-new", 999, "t-new", "room-0")

    const rooms = storedEntries()!.map((entry) => (entry as string[])[0])
    expect(rooms).toHaveLength(store.REPLAY_CHECKPOINT_LIMIT)
    expect(rooms[0]).toBe("room-0")
    expect(rooms).not.toContain("room-1")
    expect(rooms.at(-1)).toBe("room-new")
  })

  it("evicts the oldest room when no room is protected", () => {
    for (let index = 0; index <= store.REPLAY_CHECKPOINT_LIMIT; index += 1) {
      store.writeReplayCheckpoint(USER, `room-${index}`, index + 1, `t${index}`, null)
    }

    const rooms = storedEntries()!.map((entry) => (entry as string[])[0])
    expect(rooms[0]).toBe("room-1")
  })

  it("removes a rejected room and persists the removal", () => {
    store.writeReplayCheckpoint(USER, "a", 1, "t1", null)
    store.writeReplayCheckpoint(USER, "b", 2, "t2", null)

    store.removeReplayCheckpoint(USER, "a")
    store.removeReplayCheckpoint(USER, "missing")

    expect(store.peekReplayCheckpoint(USER, "a")).toBeUndefined()
    expect(storedEntries()).toStrictEqual([["b", 2, "t2"]])
  })

  it("clears memory and storage of a user", () => {
    store.writeReplayCheckpoint(USER, "a", 1, "t1", null)

    store.clearReplayCheckpoints(USER)

    expect(window.sessionStorage.getItem(KEY)).toBeNull()
    persist([["a", 5, "fresh"]])
    expect(store.peekReplayCheckpoint(USER, "a")).toStrictEqual({
      sequence: 5,
      resumeToken: "fresh",
    })
  })

  it("keeps working when storage writes and removals are denied", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota")
    })
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("denied")
    })

    store.writeReplayCheckpoint(USER, "a", 1, "t1", null)
    expect(store.peekReplayCheckpoint(USER, "a")).toStrictEqual({ sequence: 1, resumeToken: "t1" })
    store.clearReplayCheckpoints(USER)
    expect(store.peekReplayCheckpoint(USER, "a")).toBeUndefined()
  })

  it("ignores every operation of an anonymous session", () => {
    // A user literally named "undefined" shares the storage key an anonymous
    // session would use, so it proves nothing leaks across.
    persist([["room", 1, "token"]], "undefined")

    expect(store.readAndTouchReplayCheckpoint(undefined, "room")).toBeUndefined()
    expect(store.peekReplayCheckpoint(undefined, "room")).toBeUndefined()
    store.writeReplayCheckpoint(undefined, "other", 2, "t2", null)
    store.removeReplayCheckpoint(undefined, "room")
    store.clearReplayCheckpoints(undefined)

    expect(storedEntries("undefined")).toStrictEqual([["room", 1, "token"]])
  })
})
