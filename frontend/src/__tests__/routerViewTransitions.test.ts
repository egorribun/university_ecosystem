import { afterEach, describe, expect, it, vi } from "vitest"
import { execFileSync } from "node:child_process"
import { dirname, resolve } from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
} from "@tanstack/react-router"
import { configureRouterViewTransitions } from "../app/routerViewTransitions"
import { getRouter } from "../router"

function deferred() {
  let resolve!: () => void
  let reject!: (error: unknown) => void
  const promise = new Promise<void>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

type NativeUpdate = (() => Promise<void>) | { update: () => Promise<void>; types: string[] }

function nativeTransitions() {
  const records: Array<{
    ready: ReturnType<typeof deferred>
    updateDone: Promise<void>
    observeReady: ReturnType<typeof vi.spyOn>
  }> = []
  const start = vi.fn((options: NativeUpdate) => {
    records.at(-1)?.ready.reject(new DOMException("Synthetic supersession", "AbortError"))
    const ready = deferred()
    const update = typeof options === "function" ? options : options.update
    const updateDone = deferred()
    const observeReady = vi.spyOn(ready.promise, "catch")
    // The browser reports callback failures through updateCallbackDone and
    // marks ready handled before rejecting it with the same reason (W3C 7.4).
    void Promise.resolve()
      .then(update)
      .then(updateDone.resolve, (error: unknown) => {
        void ready.promise.catch(() => undefined)
        updateDone.reject(error)
        ready.reject(error)
      })
    records.push({ ready, updateDone: updateDone.promise, observeReady })
    return { ready: ready.promise, updateCallbackDone: updateDone.promise }
  })
  Object.defineProperty(document, "startViewTransition", { configurable: true, value: start })
  return { start, records }
}

afterEach(() => {
  vi.unstubAllGlobals()
  Reflect.deleteProperty(document, "startViewTransition")
})

describe("router-owned native view transitions", () => {
  it("settles reset-to-login navigation while superseding the previous animation", async () => {
    const { records } = nativeTransitions()
    const root = createRootRoute()
    const reset = createRoute({ getParentRoute: () => root, path: "/reset-password" })
    const login = createRoute({ getParentRoute: () => root, path: "/login" })
    const router = createRouter({
      routeTree: root.addChildren([reset, login]),
      history: createMemoryHistory({ initialEntries: ["/reset-password"] }),
      defaultViewTransition: true,
    })
    configureRouterViewTransitions(router)
    await router.load()
    await router.navigate({ to: "/login" })
    records.at(-1)!.ready.resolve()
    await new Promise<void>((resolve) => setTimeout(resolve, 0))
    expect(records).toHaveLength(2)
    expect(router.state.location.pathname).toBe("/login")
    expect(router.state.resolvedLocation?.pathname).toBe("/login")
    expect(router.state.status).toBe("idle")
  })

  it("finishes both updates without an unhandled AbortError when a newer transition supersedes readiness", async () => {
    const { records } = nativeTransitions()
    const router = getRouter()
    const committed: string[] = []
    const first = router.startViewTransition(async () => {
      committed.push("reset-password")
    })
    const second = router.startViewTransition(async () => {
      committed.push("login")
    })
    await Promise.all([first, second])
    records[1]!.ready.resolve()
    // Let a native unhandled rejection reach Vitest's error gate. Without an
    // owner for ready, updates still succeed but this run fails with AbortError.
    await new Promise<void>((resolve) => setTimeout(resolve, 0))
    expect(committed).toEqual(["reset-password", "login"])
  })

  it("returns the native update promise without waiting for animation readiness", async () => {
    const { records } = nativeTransitions()
    const router = getRouter()
    const update = vi.fn(async () => undefined)
    const result = router.startViewTransition(update)
    expect(result).toBe(records[0]!.updateDone)
    await result
    expect(update).toHaveBeenCalledOnce()
    records[0]!.ready.resolve()
  })

  it.each([
    new Error("Synthetic update failure"),
    new DOMException("Synthetic update abort", "AbortError"),
    undefined,
    Number.NaN,
  ])("preserves callback failures, including callback cancellation: %s", async (failure) => {
    const { records } = nativeTransitions()
    const router = getRouter()
    const result = router.startViewTransition(async () => {
      throw failure
    })
    await expect(result).rejects.toBe(failure)
    await expect(records[0]!.observeReady.mock.results[0]!.value).resolves.toBeUndefined()
    await new Promise<void>((resolve) => setTimeout(resolve, 0))
    expect(result).toBe(records[0]!.updateDone)
  })

  it("keeps a non-cancellation readiness failure observable", async () => {
    const { records } = nativeTransitions()
    const router = getRouter()
    await router.startViewTransition(async () => undefined)
    const ready = records[0]!
    const failure = new DOMException("Synthetic invalid snapshot", "InvalidStateError")
    // Observe the rejection produced by the adapter, without suppressing it in
    // production or letting this intentional non-cancellation fail the runner.
    const observed = ready.observeReady.mock.results[0]?.value as Promise<void>
    expect(observed).toBeInstanceOf(Promise)
    const rejected = expect(observed).rejects.toBe(failure)
    ready.ready.reject(failure)
    await rejected
  })

  it("keeps an independent readiness failure visible when the callback also fails", async () => {
    const { records } = nativeTransitions()
    const callbackFailure = new Error("Synthetic callback failure")
    const readinessFailure = new DOMException("Synthetic invalid snapshot", "InvalidStateError")
    const result = getRouter().startViewTransition(() => {
      throw callbackFailure
    })
    const ready = records[0]!
    const observed = ready.observeReady.mock.results[0]!.value as Promise<void>
    const rejectedReady = expect(observed).rejects.toBe(readinessFailure)
    ready.ready.reject(readinessFailure)
    await expect(result).rejects.toBe(callbackFailure)
    await rejectedReady
  })

  it.each(["Error", "AbortError"])(
    "reports exactly one unhandled callback %s in a plain native-promise process",
    (name) => {
      const adapterUrl = pathToFileURL(
        resolve(dirname(fileURLToPath(import.meta.url)), "../app/routerViewTransitions.ts")
      ).href
      const output = execFileSync(
        process.execPath,
        [
          "--conditions=browser",
          "--input-type=module",
          "-e",
          `
            const errors = []
            process.on("unhandledRejection", error => errors.push(error.name))
            globalThis.window = {}
            globalThis.self = globalThis.window
            globalThis.document = {
              startViewTransition(update) {
                let rejectReady
                let resolveUpdate
                let rejectUpdate
                const ready = new Promise((_resolve, reject) => { rejectReady = reject })
                const updateCallbackDone = new Promise((resolve, reject) => {
                  resolveUpdate = resolve
                  rejectUpdate = reject
                })
                Promise.resolve().then(update).then(resolveUpdate, error => {
                  ready.catch(() => undefined)
                  rejectUpdate(error)
                  rejectReady(error)
                })
                return { ready, updateCallbackDone }
              }
            }
            const { createMemoryHistory, createRootRoute, createRouter } = await import("@tanstack/react-router")
            const { configureRouterViewTransitions } = await import(${JSON.stringify(adapterUrl)})
            const router = createRouter({
              routeTree: createRootRoute(),
              history: createMemoryHistory(),
              defaultViewTransition: true,
            })
            configureRouterViewTransitions(router)
            router.startViewTransition(async () => {
              throw ${name === "AbortError" ? 'new DOMException("Synthetic callback abort", "AbortError")' : 'new Error("Synthetic callback failure")'}
            })
            await new Promise(resolve => setImmediate(resolve))
            process.stdout.write(JSON.stringify(errors))
          `,
        ],
        { encoding: "utf8" }
      )
      expect(JSON.parse(output)).toEqual([name])
    }
  )

  it("does not classify ordinary errors named AbortError as native cancellation", async () => {
    const { records } = nativeTransitions()
    await getRouter().startViewTransition(async () => undefined)
    const ready = records[0]!
    const failure = Object.assign(new Error("Synthetic failure"), { name: "AbortError" })
    const observed = ready.observeReady.mock.results[0]?.value as Promise<void>
    expect(observed).toBeInstanceOf(Promise)
    const rejected = expect(observed).rejects.toBe(failure)
    ready.ready.reject(failure)
    await rejected
  })

  it("honors and consumes the explicit per-navigation opt-out", async () => {
    const { start, records } = nativeTransitions()
    const router = getRouter()
    router.shouldViewTransition = false
    const update = vi.fn(async () => undefined)
    await router.startViewTransition(update)
    expect(update).toHaveBeenCalledOnce()
    expect(start).not.toHaveBeenCalled()
    expect(router.shouldViewTransition).toBeUndefined()
    await router.startViewTransition(update)
    expect(start).toHaveBeenCalledOnce()
    records[0]!.ready.resolve()
  })

  it("honors a one-navigation opt-in over a disabled default", async () => {
    const { start, records } = nativeTransitions()
    const router = getRouter()
    router.options.defaultViewTransition = false
    router.shouldViewTransition = true
    const update = vi.fn(async () => undefined)
    await router.startViewTransition(update)
    records[0]!.ready.resolve()
    await router.startViewTransition(update)
    expect(start).toHaveBeenCalledOnce()
    expect(update).toHaveBeenCalledTimes(2)
    expect(router.shouldViewTransition).toBeUndefined()
  })

  it("runs the update directly when native transitions are unavailable", async () => {
    const router = getRouter()
    const result = Promise.resolve()
    const update = vi.fn(() => result)
    expect(router.startViewTransition(update)).toBe(result)
    await result
    expect(update).toHaveBeenCalledOnce()
  })

  it("runs the update safely in a server runtime without a document", async () => {
    const { start } = nativeTransitions()
    const router = getRouter()
    vi.stubGlobal("document", undefined)
    const update = vi.fn(async () => undefined)
    await router.startViewTransition(update)
    expect(start).not.toHaveBeenCalled()
    expect(update).toHaveBeenCalledOnce()
  })

  it("preserves synchronous update errors in the direct fallback", () => {
    const router = getRouter()
    router.shouldViewTransition = false
    const failure = new Error("Synthetic synchronous update failure")
    const update = vi.fn(() => {
      throw failure
    })
    expect(() => router.startViewTransition(update)).toThrow(failure)
    expect(update).toHaveBeenCalledOnce()
    expect(router.shouldViewTransition).toBeUndefined()
  })

  it("preserves native start failures without retrying the update", () => {
    const { start } = nativeTransitions()
    const router = getRouter()
    const failure = new Error("Synthetic native start failure")
    start.mockImplementationOnce(() => {
      throw failure
    })
    const update = vi.fn(async () => undefined)
    expect(() => router.startViewTransition(update)).toThrow(failure)
    expect(update).not.toHaveBeenCalled()
    expect(router.shouldViewTransition).toBeUndefined()
  })

  it("passes static transition types through when the browser supports them", async () => {
    const { start, records } = nativeTransitions()
    vi.stubGlobal("CSS", { supports: () => true })
    const router = getRouter()
    router.shouldViewTransition = { types: ["backwards"] }
    const update = vi.fn(async () => undefined)
    await router.startViewTransition(update)
    expect(start).toHaveBeenCalledWith({ update: expect.any(Function), types: ["backwards"] })
    expect(update).toHaveBeenCalledOnce()
    expect(router.shouldViewTransition).toBeUndefined()
    records[0]!.ready.resolve()
  })

  it("resolves dynamic types using the same location-change information", async () => {
    const { start, records } = nativeTransitions()
    vi.stubGlobal("CSS", { supports: () => true })
    const router = getRouter()
    const from = router.buildLocation({ to: "/reset-password" })
    const to = router.buildLocation({ to: "/login" })
    router.stores.resolvedLocation.set(from)
    router.latestLocation = to
    const types = vi.fn(() => ["forwards"])
    router.shouldViewTransition = { types }
    const update = vi.fn(async () => undefined)
    await router.startViewTransition(update)
    expect(types).toHaveBeenCalledWith({
      fromLocation: from,
      toLocation: to,
      pathChanged: true,
      hrefChanged: true,
      hashChanged: false,
    })
    expect(start).toHaveBeenCalledWith({ update: expect.any(Function), types: ["forwards"] })
    expect(update).toHaveBeenCalledOnce()
    records[0]!.ready.resolve()
  })

  it("respects a dynamic-types opt-out without starting an animation", async () => {
    const { start } = nativeTransitions()
    vi.stubGlobal("CSS", { supports: () => true })
    const router = getRouter()
    router.shouldViewTransition = { types: () => false }
    const result = Promise.resolve()
    const update = vi.fn(() => result)
    expect(router.startViewTransition(update)).toBe(result)
    await result
    expect(start).not.toHaveBeenCalled()
    expect(update).toHaveBeenCalledOnce()
    expect(router.shouldViewTransition).toBeUndefined()
  })

  it.each([undefined, {}, { supports: () => false }])(
    "retains ordinary transition fallback without types-selector support: %s",
    async (css) => {
      const { start, records } = nativeTransitions()
      vi.stubGlobal("CSS", css)
      const router = getRouter()
      const types = vi.fn(() => false as const)
      router.shouldViewTransition = { types }
      const update = vi.fn(async () => undefined)
      await router.startViewTransition(update)
      expect(types).not.toHaveBeenCalled()
      expect(start).toHaveBeenCalledWith(expect.any(Function))
      expect(update).toHaveBeenCalledOnce()
      records[0]!.ready.resolve()
    }
  )
})
