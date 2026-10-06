import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { dehydrate, hydrate, MutationObserver, QueryClient } from "@tanstack/react-query"
import type { PersistedClient } from "@tanstack/react-query-persist-client"
import { rotateBrowserSession } from "@/stores/sessionEpoch"
import { useAuthStore } from "@/stores/useAuthStore"
import { testUser } from "@/tests/mocks/handlers"

const idb = vi.hoisted(() => ({
  values: new Map<IDBValidKey, PersistedClient>(),
  beforeSet: undefined as undefined | (() => Promise<void>),
  beforeGet: undefined as undefined | (() => Promise<void>),
  beforeDelete: undefined as undefined | ((key: IDBValidKey) => Promise<void>),
}))
vi.mock("idb-keyval", () => ({
  set: async (key: IDBValidKey, value: PersistedClient) => {
    await idb.beforeSet?.()
    idb.values.set(key, structuredClone(value))
  },
  get: async (key: IDBValidKey) => {
    const value = idb.values.get(key)
    await idb.beforeGet?.()
    return value ? structuredClone(value) : undefined
  },
  del: async (key: IDBValidKey) => {
    await idb.beforeDelete?.(key)
    idb.values.delete(key)
  },
}))
import { createQueryClient, idbPersister } from "../queryClient"
import { createSessionMutationCache } from "../sessionMutationCache"

function account(id: string | null) {
  rotateBrowserSession()
  useAuthStore.setState({ user: id ? { ...testUser, id } : null, loading: false })
}
function client(owner: string): PersistedClient {
  const queryClient = createQueryClient()
  queryClient.setQueryData(["users", "me"], { ...testUser, id: owner })
  queryClient.setQueryData(["chats"], [{ content: `private ${owner}` }])
  queryClient.getMutationCache().build(
    queryClient,
    { mutationKey: ["private-change"] },
    {
      context: undefined,
      data: undefined,
      error: null,
      failureCount: 0,
      failureReason: null,
      isPaused: true,
      status: "pending",
      variables: { content: `pending ${owner}` },
      submittedAt: 1,
    }
  )
  return { timestamp: Date.now(), buster: "1.0.0", clientState: dehydrate(queryClient) }
}
function deferred() {
  let resolve!: () => void
  const promise = new Promise<void>((done) => {
    resolve = done
  })
  return { promise, resolve }
}
beforeEach(() => {
  account(null)
  idb.values.clear()
  idb.beforeGet = undefined
  idb.beforeSet = undefined
  idb.beforeDelete = undefined
})
afterEach(() => {
  account(null)
  vi.unstubAllGlobals()
})

describe("application query persistence isolation", () => {
  it("never hydrates legacy queries or pending mutations while signed out", async () => {
    idb.values.set("reactQuery", client("A"))
    expect(await idbPersister.restoreClient()).toBeUndefined()
    await idbPersister.persistClient(client("A"))
    expect(idb.values.has("reactQuery")).toBe(false)
    expect(idb.values.size).toBe(0)
  })

  it("restores same-account offline queries and mutations but never gives them to B", async () => {
    account("A")
    await idbPersister.persistClient(client("A"))
    const same = await idbPersister.restoreClient()
    const restored = createQueryClient()
    expect(same).toBeDefined()
    hydrate(restored, same!.clientState)
    expect(restored.getQueryData(["chats"])).toEqual([{ content: "private A" }])
    expect(restored.getMutationCache().getAll()[0]?.state.variables).toEqual({
      content: "pending A",
    })
    account("B")
    expect(await idbPersister.restoreClient()).toBeUndefined()
  })

  it("invalidates both queries and mutations between restore and hydration", async () => {
    account("A")
    await idbPersister.persistClient(client("A"))
    const snapshot = await idbPersister.restoreClient()
    account("B")
    const restored = createQueryClient()
    expect(snapshot).toBeDefined()
    hydrate(restored, snapshot!.clientState)
    expect(restored.getQueryCache().getAll()).toEqual([])
    expect(restored.getMutationCache().getAll()).toEqual([])
  })

  it("rejects a snapshot whose profile belongs to a different account", async () => {
    account("B")
    await idbPersister.persistClient(client("A"))
    expect(idb.values.size).toBe(0)
  })

  it("drops an old restore if the account changes while IndexedDB is reading", async () => {
    account("A")
    await idbPersister.persistClient(client("A"))
    const entered = deferred()
    const release = deferred()
    idb.beforeGet = async () => {
      entered.resolve()
      await release.promise
    }
    const restoring = idbPersister.restoreClient()
    await entered.promise
    account("B")
    release.resolve()
    expect(await restoring).toBeUndefined()
  })

  it("rolls back an old write after logout even if the same account logs in again", async () => {
    account("A")
    const entered = deferred()
    const release = deferred()
    idb.beforeSet = async () => {
      entered.resolve()
      await release.promise
    }
    const writing = idbPersister.persistClient(client("A"))
    await entered.promise
    account(null)
    account("A")
    release.resolve()
    await writing
    expect(idb.values.size).toBe(0)
  })
})

describe("mutation callback session ownership", () => {
  it.each(["success", "error"])(
    "drops late %s callbacks and per-call callbacks after account change",
    async (outcome) => {
      account("A")
      const queryClient = createQueryClient()
      queryClient.setQueryData(["chats"], ["private A"])
      let resolve!: (value: string) => void
      let reject!: (reason: Error) => void
      const pending = new Promise<string>((ok, fail) => {
        resolve = ok
        reject = fail
      })
      const rollback = () => queryClient.setQueryData(["chats"], ["private A"])
      const observer = new MutationObserver(queryClient, {
        mutationFn: () => pending,
        onSuccess: rollback,
        onError: rollback,
        onSettled: rollback,
      })
      const unsubscribe = observer.subscribe(() => undefined)
      const perCall = vi.fn(rollback)
      const mutation = observer
        .mutate(undefined, { onSuccess: perCall, onError: perCall, onSettled: perCall })
        .catch(() => undefined)
      await Promise.resolve()
      queryClient.clear()
      account("B")
      queryClient.setQueryData(["users", "me"], { ...testUser, id: "B" })
      queryClient.setQueryData(["chats"], ["private B"])
      observer.setOptions({
        mutationFn: () => pending,
        onSuccess: rollback,
        onError: rollback,
        onSettled: rollback,
      })
      if (outcome === "success") resolve("A result")
      else reject(new Error("A rejected"))
      await mutation
      expect(queryClient.getQueryData(["chats"])).toEqual(["private B"])
      expect(perCall).not.toHaveBeenCalled()
      unsubscribe()
    }
  )

  it("runs an optimistic callback while its creating session still owns the mutation", async () => {
    account("A")
    const queryClient = createQueryClient()
    queryClient.setQueryData(["chats"], ["private A"])
    const onMutate = vi.fn(async () => {
      queryClient.setQueryData(["chats"], ["optimistic A"])
    })
    const mutationFn = vi.fn(async () => "saved")
    const observer = new MutationObserver(queryClient, { mutationFn, onMutate })
    const unsubscribe = observer.subscribe(() => undefined)

    try {
      await expect(observer.mutate(undefined)).resolves.toBe("saved")
      expect(onMutate).toHaveBeenCalledTimes(1)
      expect(mutationFn).toHaveBeenCalledTimes(1)
      expect(queryClient.getQueryData(["chats"])).toEqual(["optimistic A"])
    } finally {
      unsubscribe()
      queryClient.clear()
    }
  })
  it("stops an optimistic callback suspended in cancelQueries across account switch", async () => {
    account("A")
    const queryClient = createQueryClient()
    const mutate = vi.fn(async () => "done")
    const observer = new MutationObserver(queryClient, {
      mutationFn: mutate,
      onMutate: async () => {
        await queryClient.cancelQueries({ queryKey: ["chats"] })
        queryClient.setQueryData(["chats"], ["old optimistic A"])
      },
    })
    const mutation = observer.mutate(undefined).catch(() => undefined)
    account("B")
    queryClient.setQueryData(["chats"], ["private B"])
    await mutation
    expect(queryClient.getQueryData(["chats"])).toEqual(["private B"])
    expect(mutate).not.toHaveBeenCalled()
  })
})

describe("persistent query queue recovery", () => {
  it("drops a write queued behind a retired account and lets the new account persist", async () => {
    account("A")
    const entered = deferred()
    const release = deferred()
    idb.beforeSet = async () => {
      entered.resolve()
      await release.promise
    }
    const first = idbPersister.persistClient(client("A"))
    await entered.promise
    const queued = idbPersister.persistClient(client("A"))
    account("B")
    idb.beforeSet = undefined
    const successor = idbPersister.persistClient(client("B"))
    release.resolve()
    await Promise.all([first, queued, successor])
    expect([...idb.values.keys()]).toEqual(["reactQuery:v2:B"])
  })

  it("recovers its queue after a failed write and a failed scoped removal", async () => {
    account("A")
    idb.beforeSet = async () => {
      throw new Error("database unavailable")
    }
    await expect(idbPersister.persistClient(client("A"))).rejects.toThrow("database unavailable")
    idb.beforeSet = undefined
    await idbPersister.persistClient(client("A"))
    idb.beforeDelete = async (key) => {
      if (key === "reactQuery:v2:A") throw new Error("delete unavailable")
    }
    await expect(idbPersister.removeClient()).rejects.toThrow("delete unavailable")
    idb.beforeDelete = undefined
    await idbPersister.removeClient()
    expect(idb.values.size).toBe(0)
    await idbPersister.persistClient(client("A"))
    expect(idb.values.has("reactQuery:v2:A")).toBe(true)
  })

  it("removes the captured account only after its pending write completes", async () => {
    account("A")
    const entered = deferred()
    const release = deferred()
    idb.beforeSet = async () => {
      entered.resolve()
      await release.promise
    }
    const writing = idbPersister.persistClient(client("A"))
    await entered.promise
    const removing = idbPersister.removeClient()
    release.resolve()
    await Promise.all([writing, removing])
    expect(idb.values.size).toBe(0)
  })

  it("clears live clients even when a collected browser client remains in the registry", () => {
    const live = createQueryClient()
    live.setQueryData(["chats"], ["private A"])
    vi.stubGlobal(
      "WeakRef",
      class {
        deref() {
          return undefined
        }
      }
    )
    createQueryClient()
    account("B")
    expect(live.getQueryCache().getAll()).toEqual([])
  })
})

describe("mutation dispatch and observer reuse", () => {
  it.each([false, true])(
    "blocks an expired mutation before dispatch (optimistic=%s)",
    async (optimistic) => {
      account("A")
      const queryClient = createQueryClient()
      const mutationFn = vi.fn(async () => "done")
      const onMutate = vi.fn()
      const mutation = queryClient
        .getMutationCache()
        .build(queryClient, { mutationFn, ...(optimistic ? { onMutate } : {}) })
      account("B")
      await expect(mutation.execute(undefined)).rejects.toMatchObject({ silent: true })
      expect(mutationFn).not.toHaveBeenCalled()
      expect(onMutate).not.toHaveBeenCalled()
    }
  )

  it("reuses an observer for a fresh mutation and preserves same-session error callbacks", async () => {
    account("A")
    const queryClient = createQueryClient()
    const onError = vi.fn()
    const observer = new MutationObserver(queryClient, {
      mutationFn: async () => {
        throw new Error("rejected")
      },
      onError,
    })
    const unsubscribe = observer.subscribe(() => undefined)
    await expect(observer.mutate(undefined)).rejects.toThrow("rejected")
    await expect(observer.mutate(undefined)).rejects.toThrow("rejected")
    expect(onError).toHaveBeenCalledTimes(2)
    unsubscribe()
  })
})

it("binds a replayed observer event even when its mutation registration predates the session cache", async () => {
  account("A")
  const externalClient = new QueryClient()
  const response = deferred()
  const callback = vi.fn()
  const observer = new MutationObserver(externalClient, { mutationFn: () => response.promise })
  const unsubscribe = observer.subscribe(() => undefined)
  const pending = observer.mutate(undefined, { onSuccess: callback })
  const mutation = externalClient.getMutationCache().getAll()[0]!
  const sessionCache = createSessionMutationCache()
  sessionCache.notify({ type: "observerAdded", mutation, observer })
  account("B")
  response.resolve()
  await pending
  expect(callback).not.toHaveBeenCalled()
  expect(observer.getCurrentResult().status).toBe("idle")
  unsubscribe()
  externalClient.clear()
})
