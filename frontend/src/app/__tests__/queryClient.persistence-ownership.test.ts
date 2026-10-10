import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { dehydrate, hydrate, type QueryKey } from "@tanstack/react-query"
import type { PersistedClient } from "@tanstack/react-query-persist-client"
import { clear, get, keys, set } from "idb-keyval"
import {
  acceptBrowserSessionGeneration,
  captureSessionEpoch,
  rotateBrowserSession,
} from "@/stores/sessionEpoch"
import { useAuthStore } from "@/stores/useAuthStore"
import { testUser } from "@/tests/mocks/handlers"

// Keep real IndexedDB transactions and structured cloning. Only the delivery of
// an operation's result is held, so account transitions can occur while the
// application is still awaiting the browser's response.
const io = vi.hoisted(() => ({
  afterRead: undefined as undefined | ((key: IDBValidKey) => Promise<void>),
  afterWrite: undefined as undefined | ((key: IDBValidKey) => Promise<void>),
  beforeDelete: undefined as undefined | ((key: IDBValidKey) => Promise<void>),
  readError: undefined as Error | undefined,
  writeError: undefined as Error | undefined,
}))
vi.mock("idb-keyval", async (importOriginal) => {
  const actual = await importOriginal<typeof import("idb-keyval")>()
  return {
    ...actual,
    get: async (key: IDBValidKey) => {
      if (io.readError) throw io.readError
      const result = await actual.get(key)
      await io.afterRead?.(key)
      return result
    },
    set: async (key: IDBValidKey, value: unknown) => {
      if (io.writeError) throw io.writeError
      await actual.set(key, value)
      await io.afterWrite?.(key)
    },
    del: async (key: IDBValidKey) => {
      await io.beforeDelete?.(key)
      await actual.del(key)
    },
  }
})

import { createQueryClient, idbPersister, setQueryCacheIdentity } from "../queryClient"

const sessionKey = "ecosystem.session.generation.v1"
const accountKey = (owner: string) => `reactQuery:v2:${encodeURIComponent(owner)}`

function publishAccount(id: string | null) {
  useAuthStore.setState({ user: id === null ? null : { ...testUser, id }, loading: false })
}

function snapshot(owner: string, profileKey: QueryKey = ["users", "me"]): PersistedClient {
  const source = createQueryClient()
  source.setQueryData(profileKey, { ...testUser, id: owner })
  source.setQueryData(["schedule"], [`schedule for ${owner}`])
  const saved = { timestamp: Date.now(), buster: "1.0.0", clientState: dehydrate(source) }
  source.clear()
  return saved
}

function pause() {
  let release!: () => void
  const pending = new Promise<void>((resolve) => {
    release = resolve
  })
  let entered = false
  return {
    hold: async () => {
      entered = true
      await pending
    },
    entered: () => entered,
    release,
  }
}

beforeEach(async () => {
  io.afterRead = undefined
  io.afterWrite = undefined
  io.beforeDelete = undefined
  io.readError = undefined
  io.writeError = undefined
  rotateBrowserSession()
  publishAccount(null)
  await clear()
})

afterEach(async () => {
  io.afterRead = undefined
  io.afterWrite = undefined
  io.beforeDelete = undefined
  io.readError = undefined
  io.writeError = undefined
  publishAccount(null)
  await clear()
})

describe("confirmed profile persistence", () => {
  it.each([
    ["settings", "me"],
    ["users", "other"],
    ["settings", "other"],
  ])("rejects an id attached to the unrelated %s/%s query", async (root, leaf) => {
    publishAccount("A")
    const unrelated = snapshot("A", [root, leaf])

    await idbPersister.persistClient(unrelated)
    expect(await keys()).toEqual([])

    await set(accountKey("A"), unrelated)
    expect(await idbPersister.restoreClient()).toBeUndefined()
  })

  it("does not infer an owner from an unresolved profile query", async () => {
    publishAccount("A")
    const source = createQueryClient()
    source.getQueryCache().build(source, { queryKey: ["users", "me"] })
    source.setQueryData(["schedule"], ["unconfirmed schedule"])
    // Exercise the public persister's defensive boundary. The application's
    // configured provider itself dehydrates only successful queries.
    const saved = {
      timestamp: Date.now(),
      buster: "1.0.0",
      clientState: dehydrate(source, { shouldDehydrateQuery: () => true }),
    }
    source.clear()

    await expect(idbPersister.persistClient(saved)).resolves.toBeUndefined()
    expect(await keys()).toEqual([])
    await set(accountKey("A"), saved)
    await expect(idbPersister.restoreClient()).resolves.toBeUndefined()
  })

  it("keeps account namespaces distinct when an id contains reserved URL characters", async () => {
    publishAccount("A/B:C")
    await idbPersister.persistClient(snapshot("A/B:C"))
    expect(await keys()).toEqual(["reactQuery:v2:A%2FB%3AC"])
    const restored = await idbPersister.restoreClient()
    const target = createQueryClient()
    hydrate(target, restored!.clientState)
    expect(target.getQueryData(["schedule"])).toEqual(["schedule for A/B:C"])
  })

  it("keeps confirmed in-memory data during an ordinary same-account refresh", async () => {
    publishAccount("A")
    const active = createQueryClient()
    active.setQueryData(["schedule"], ["current schedule"])
    const owns = captureSessionEpoch()

    useAuthStore.setState({ loading: true })
    expect(active.getQueryData(["schedule"])).toEqual(["current schedule"])
    expect(owns()).toBe(true)
    await idbPersister.persistClient(snapshot("A"))
    expect(await get(accountKey("A"))).toBeDefined()

    useAuthStore.setState({ loading: false })
    expect(active.getQueryData(["schedule"])).toEqual(["current schedule"])
    expect(owns()).toBe(true)
  })

  it("retires the old cache when a different profile is still loading", async () => {
    publishAccount("A")
    const active = createQueryClient()
    active.setQueryData(["schedule"], ["old schedule"])
    const outgoing = snapshot("A")
    useAuthStore.setState({ user: { ...testUser, id: "B" }, loading: true })

    expect(active.getQueryCache().getAll()).toEqual([])
    await idbPersister.persistClient(outgoing)
    expect(await keys()).toEqual([])
  })

  it("invalidates suspended work when identity changes without rotating the browser session", async () => {
    publishAccount("A")
    const active = createQueryClient()
    const canceling = active.cancelQueries()
    // Profile publication precedes rendering and need not be accompanied by a
    // browser-generation update, for example during an auth refresh.
    publishAccount("B")
    await expect(canceling).rejects.toMatchObject({ silent: true })
  })

  it("requires a browser generation even when network auth confirms the profile", async () => {
    localStorage.removeItem(sessionKey)
    acceptBrowserSessionGeneration()
    publishAccount("A")
    const saved = snapshot("A")
    await idbPersister.persistClient(saved)
    expect(await keys()).toEqual([])

    await set(accountKey("A"), saved)
    await set("reactQuery", saved)
    expect(await idbPersister.restoreClient()).toBeUndefined()
    expect(await get("reactQuery")).toBeUndefined()
  })

  it("restores the profile confirmed while legacy deletion was pending", async () => {
    const saved = snapshot("A")
    await set(accountKey("A"), saved)
    useAuthStore.setState({ user: { ...testUser, id: "ssr-stub" }, loading: true })
    const legacyDeletion = pause()
    io.beforeDelete = legacyDeletion.hold
    const restoring = idbPersister.restoreClient()
    try {
      await vi.waitFor(() => expect(legacyDeletion.entered()).toBe(true))
      legacyDeletion.release()
      publishAccount("A")
      expect(await restoring).toEqual(saved)
    } finally {
      legacyDeletion.release()
      publishAccount(null)
      await Promise.allSettled([restoring])
    }
  })

  it("ignores the old confirmed profile during publication of a different cache owner", async () => {
    publishAccount("A")
    await set(accountKey("A"), snapshot("A"))
    // This is the ordering used by applyUserState: the cache owner is published
    // before React's profile state is mirrored to the auth store.
    setQueryCacheIdentity("B")
    expect(await idbPersister.restoreClient()).toBeUndefined()
  })

  it("propagates a storage read failure while the confirmed profile still owns the cache", async () => {
    publishAccount("A")
    await set(accountKey("A"), snapshot("A"))
    const failure = new DOMException("Read transaction aborted", "AbortError")
    io.readError = failure

    await expect(idbPersister.restoreClient()).rejects.toBe(failure)
  })

  it("drops a retired profile before attempting unavailable storage", async () => {
    publishAccount("A")
    await set(accountKey("A"), snapshot("A"))
    setQueryCacheIdentity("B")
    io.readError = new DOMException("Read transaction aborted", "AbortError")

    await expect(idbPersister.restoreClient()).resolves.toBeUndefined()
  })
})

describe("asynchronous persistence ownership", () => {
  it("rejects an in-flight restore when only the browser session rotates", async () => {
    publishAccount("A")
    await idbPersister.persistClient(snapshot("A"))
    const read = pause()
    io.afterRead = read.hold
    const restoring = idbPersister.restoreClient()
    try {
      await vi.waitFor(() => expect(read.entered()).toBe(true))
      rotateBrowserSession()
      read.release()
      expect(await restoring).toBeUndefined()
    } finally {
      read.release()
      await Promise.allSettled([restoring])
    }
    io.afterRead = undefined
    // Rotation retires the in-flight operation, not this account's saved data.
    expect(await idbPersister.restoreClient()).toBeDefined()
  })

  it("preserves the new same-account snapshot while an outgoing write retires", async () => {
    publishAccount("A")
    const write = pause()
    io.afterWrite = write.hold
    const outgoing = idbPersister.persistClient(snapshot("A"))
    let successor: ReturnType<typeof idbPersister.persistClient> | undefined
    try {
      await vi.waitFor(() => expect(write.entered()).toBe(true))
      rotateBrowserSession()
      io.afterWrite = undefined
      const saved = snapshot("A")
      const schedule = saved.clientState.queries.find((query) => query.queryKey[0] === "schedule")!
      schedule.state.data = ["new session schedule"]
      successor = idbPersister.persistClient(saved)
      write.release()
      await Promise.all([outgoing, successor])
      expect(await get(accountKey("A"))).toEqual(saved)
    } finally {
      write.release()
      await Promise.allSettled([outgoing, successor])
    }
  })

  it("drops retired queued writes before attempting unavailable storage", async () => {
    publishAccount("A")
    const write = pause()
    io.afterWrite = write.hold
    const first = idbPersister.persistClient(snapshot("A"))
    let queued: ReturnType<typeof idbPersister.persistClient> | undefined
    try {
      await vi.waitFor(() => expect(write.entered()).toBe(true))
      queued = idbPersister.persistClient(snapshot("A"))
      rotateBrowserSession()
      io.writeError = new Error("IndexedDB write unavailable")
      write.release()
      await expect(Promise.all([first, queued])).resolves.toEqual([undefined, undefined])
      expect(await keys()).toEqual([])
    } finally {
      write.release()
      await Promise.allSettled([first, queued])
    }
    io.writeError = undefined
    io.afterWrite = undefined
    await idbPersister.persistClient(snapshot("A"))
    expect(await get(accountKey("A"))).toBeDefined()
  })

  it("keeps a stale restore retired through an A-to-B-to-A identity transition", async () => {
    publishAccount("A")
    await idbPersister.persistClient(snapshot("A"))
    const read = pause()
    io.afterRead = read.hold
    const restoring = idbPersister.restoreClient()
    try {
      await vi.waitFor(() => expect(read.entered()).toBe(true))
      publishAccount("B")
      publishAccount("A")
      read.release()
      expect(await restoring).toBeUndefined()
    } finally {
      read.release()
      await Promise.allSettled([restoring])
    }
  })

  it("removes the captured account if identity changes while legacy deletion is pending", async () => {
    publishAccount("A")
    await idbPersister.persistClient(snapshot("A"))
    publishAccount("B")
    await idbPersister.persistClient(snapshot("B"))
    publishAccount("A")
    const legacyDeletion = pause()
    io.beforeDelete = async (key) => {
      if (key === "reactQuery") await legacyDeletion.hold()
    }
    const removing = idbPersister.removeClient()
    try {
      await vi.waitFor(() => expect(legacyDeletion.entered()).toBe(true))
      publishAccount("B")
      legacyDeletion.release()
      await removing
      expect(await get(accountKey("A"))).toBeUndefined()
      expect(await get(accountKey("B"))).toBeDefined()
    } finally {
      legacyDeletion.release()
      await Promise.allSettled([removing])
    }
  })

  it.each(["A", "null"])(
    "preserves account %s while removing the legacy snapshot signed out",
    async (owner) => {
      const saved = snapshot(owner)
      await set("reactQuery", saved)
      await set(accountKey(owner), saved)
      await idbPersister.removeClient()
      expect(await keys()).toEqual([accountKey(owner)])
    }
  )
})
