import { afterEach, describe, expect, it, vi } from "vitest"
import { QueryClient, type MutationCacheNotifyEvent } from "@tanstack/react-query"
import { createSessionMutationCache } from "../sessionMutationCache"

const generationKey = "ecosystem.session.generation.v1"

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

const clients: QueryClient[] = []

function sessionClient() {
  const client = new QueryClient({ mutationCache: createSessionMutationCache() })
  clients.push(client)
  return client
}

afterEach(() => {
  clients.splice(0).forEach((client) => client.clear())
  vi.restoreAllMocks()
})

describe("createSessionMutationCache storage fence", () => {
  it("ignores storage events for unrelated keys while a mutation is in flight", async () => {
    const client = sessionClient()
    const started = deferred<void>()
    const response = deferred<string>()
    const onSuccess = vi.fn()
    const mutation = client.getMutationCache().build(client, {
      mutationFn: () => {
        started.resolve()
        return response.promise
      },
      onSuccess,
    })

    const pending = mutation.execute(undefined)
    await started.promise
    window.dispatchEvent(new StorageEvent("storage", { key: "unrelated.setting", newValue: "1" }))
    response.resolve("done")
    await pending

    expect(onSuccess).toHaveBeenCalledOnce()
  })

  it("retires an in-flight mutation on the session generation key", async () => {
    const client = sessionClient()
    const started = deferred<void>()
    const response = deferred<string>()
    const onSuccess = vi.fn()
    const mutation = client.getMutationCache().build(client, {
      mutationFn: () => {
        started.resolve()
        return response.promise
      },
      onSuccess,
    })

    const pending = mutation.execute(undefined).catch(() => undefined)
    await started.promise
    window.dispatchEvent(
      new StorageEvent("storage", { key: generationKey, newValue: '{"nonce":"other"}' })
    )
    response.resolve("stale")
    await pending

    expect(onSuccess).not.toHaveBeenCalled()
  })

  it("keeps a live owner fenced when replayed lifecycle events name an unregistered mutation", async () => {
    const sessionCache = createSessionMutationCache()
    const external = new QueryClient()
    clients.push(external)
    const settled = await external
      .getMutationCache()
      .build(external, { mutationFn: async () => "external" })
      .execute(undefined)
    expect(settled).toBe("external")
    const foreign = external.getMutationCache().getAll()[0]!

    // Replayed lifecycle events for a mutation this cache never registered
    // have no owner to release, so the live owner below must stay fenced.
    sessionCache.notify({ type: "removed", mutation: foreign } as MutationCacheNotifyEvent)
    sessionCache.notify({
      type: "updated",
      mutation: foreign,
      action: { type: "success" },
    } as unknown as MutationCacheNotifyEvent)

    const client = new QueryClient({ mutationCache: sessionCache })
    clients.push(client)
    const started = deferred<void>()
    const response = deferred<string>()
    const onSuccess = vi.fn()
    const live = client.getMutationCache().build(client, {
      mutationFn: () => {
        started.resolve()
        return response.promise
      },
      onSuccess,
    })
    const pending = live.execute(undefined).catch(() => undefined)
    await started.promise
    window.dispatchEvent(
      new StorageEvent("storage", { key: generationKey, newValue: '{"nonce":"other"}' })
    )
    response.resolve("stale")
    await pending

    expect(onSuccess).not.toHaveBeenCalled()
  })
})
