import type { MutableRefObject, PropsWithChildren } from "react"
import { act, renderHook, waitFor, cleanup } from "@testing-library/react"
import { renderToString } from "react-dom/server"
import { QueryClientProvider } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"

import api from "@/api/client"
import { createQueryClient } from "@/app/queryClient"
import { testUser } from "@/tests/mocks/handlers"
import {
  PROFILE_CACHE_STORAGE_KEY,
  useProfileSync,
  type SsrAuthHint,
} from "@/hooks/auth/useProfileSync"

const signingKey = "a".repeat(32)

type RuntimeProps = {
  ensureSessionSigningKey: () => Promise<string | null>
}

const renderRuntime = (
  ensureSessionSigningKey: () => Promise<string | null>,
  initialSigningKey: string | null = signingKey,
  providedQueryClient?: ReturnType<typeof createQueryClient>
) => {
  const queryClient = providedQueryClient ?? createQueryClient()
  const updateSessionSigningKey = vi.fn()
  const signingKeyRef = { current: initialSigningKey } as MutableRefObject<string | null>
  const signingKeyPromiseRef = { current: null } as MutableRefObject<Promise<string | null> | null>
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  const view = renderHook(
    ({ ensureSessionSigningKey: ensure }: RuntimeProps) =>
      useProfileSync(updateSessionSigningKey, signingKeyRef, signingKeyPromiseRef, ensure),
    {
      initialProps: { ensureSessionSigningKey },
      wrapper,
    }
  )

  return { ...view, queryClient }
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllEnvs()
})

describe("useProfileSync runtime defensive paths", () => {
  it("uses the role-only SSR hint during browser hydration", () => {
    const queryClient = createQueryClient()
    vi.spyOn(queryClient, "fetchQuery").mockReturnValue(new Promise(() => undefined) as never)
    const signingKeyRef = { current: null } as MutableRefObject<string | null>
    const promiseRef = { current: null } as MutableRefObject<Promise<string | null> | null>
    const ensureSessionSigningKey = vi.fn(async () => null)
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )

    const view = renderHook(
      () =>
        useProfileSync(vi.fn(), signingKeyRef, promiseRef, ensureSessionSigningKey, {
          isAuth: true,
          user: { role: "teacher" },
        }),
      { wrapper }
    )

    expect(view.result.current.user).toMatchObject({ id: "ssr-stub", role: "teacher" })
    view.unmount()
  })

  it("skips cross-tab cache synchronization when the browser runtime is incomplete", () => {
    const originalWindow = globalThis.window
    const queryClient = createQueryClient()
    vi.spyOn(queryClient, "fetchQuery").mockReturnValue(new Promise(() => undefined) as never)
    // A server-like global can expose a document object while lacking a
    // location. The cache listener must fail closed instead of subscribing.
    vi.stubGlobal("window", { document: globalThis.document, location: undefined })

    try {
      const view = renderRuntime(
        vi.fn(async () => null),
        null,
        queryClient
      )
      expect(view.result.current.loading).toBe(true)
      view.unmount()
    } finally {
      vi.stubGlobal("window", originalWindow)
    }
  })

  it("uses the LHCI user without fetching the profile", async () => {
    vi.stubEnv("VITE_LHCI", "true")
    const getSpy = vi.spyOn(api, "get")

    const { result } = renderRuntime(
      vi.fn(async () => null),
      null
    )

    // The synthetic audit identity must be available during the very first
    // client render.  Waiting for the effect would leave SSR markup hydrated
    // with an anonymous user and postpone the first meaningful paint until
    // React commits the follow-up state update.
    expect(result.current.user?.id).toBe("lhci-mock-user")
    expect(result.current.loading).toBe(false)
    await act(async () => {
      await Promise.resolve()
    })
    expect(result.current.user?.id).toBe("lhci-mock-user")
    await waitFor(() => expect(result.current.user?.id).toBe("lhci-mock-user"))
    expect(result.current.loading).toBe(false)
    expect(getSpy).not.toHaveBeenCalled()
  })

  it("restores the synthetic user when an LHCI render was replaced", async () => {
    vi.stubEnv("VITE_LHCI", "true")
    const queryClient = createQueryClient()
    vi.spyOn(queryClient, "fetchQuery").mockReturnValue(new Promise(() => undefined) as never)
    const view = renderRuntime(
      vi.fn(async () => null),
      null,
      queryClient
    )
    expect(view.result.current.user?.id).toBe("lhci-mock-user")

    await act(async () => {
      view.result.current.setUser({ ...testUser, id: "temporary-user" } as never)
      await Promise.resolve()
    })

    const replacementEnsure = vi.fn(async () => null)
    view.rerender({ ensureSessionSigningKey: replacementEnsure })
    await waitFor(() => expect(view.result.current.user?.id).toBe("lhci-mock-user"))
    view.unmount()
  })

  it("starts a cold profile fetch after an authenticated audit state is cleared", async () => {
    vi.stubEnv("VITE_LHCI", "true")
    const queryClient = createQueryClient()
    vi.spyOn(queryClient, "fetchQuery").mockReturnValue(new Promise(() => undefined) as never)
    const view = renderRuntime(
      vi.fn(async () => null),
      null,
      queryClient
    )
    expect(view.result.current.user?.id).toBe("lhci-mock-user")

    // Switch back to the normal runtime and clear the synthetic identity. A
    // dependency change then exercises the cold-start condition: no user,
    // no cache, not initializing, and no previous fetch attempt.
    vi.stubEnv("VITE_LHCI", "false")
    await act(async () => {
      view.result.current.setUser(null)
      await Promise.resolve()
    })
    view.rerender({ ensureSessionSigningKey: vi.fn(async () => null) })

    await waitFor(() => expect(view.result.current.loading).toBe(true))
    expect(queryClient.fetchQuery).toHaveBeenCalled()
    view.unmount()
  })

  it("swallows a localStorage exception thrown during cache migration", async () => {
    localStorage.setItem(PROFILE_CACHE_STORAGE_KEY, JSON.stringify({ cached: true }))
    const descriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage")
    const storage = window.localStorage
    let accesses = 0

    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      get: () => {
        accesses += 1
        if (accesses >= 3) throw new Error("private browsing")
        return storage
      },
    })

    try {
      const { result } = renderRuntime(
        vi.fn(async () => null),
        null
      )
      await waitFor(() => expect(result.current.loading).toBe(false))
      expect(accesses).toBeGreaterThanOrEqual(3)
    } finally {
      if (descriptor) Object.defineProperty(globalThis, "localStorage", descriptor)
    }
  })

  it("marks an automatic fetch as attempted and skips a dependency-only duplicate", async () => {
    localStorage.clear()
    vi.spyOn(api, "get").mockResolvedValue({ data: testUser } as never)
    const firstEnsure = vi.fn(async () => null)
    const view = renderRuntime(firstEnsure, null)

    await waitFor(() => expect(api.get).toHaveBeenCalledOnce())
    await waitFor(() => expect(view.result.current.loading).toBe(false))

    const replacementEnsure = vi.fn(async () => null)
    view.rerender({ ensureSessionSigningKey: replacementEnsure })
    await waitFor(() => expect(view.result.current.loading).toBe(false))

    expect(api.get).toHaveBeenCalledOnce()
    expect(replacementEnsure).not.toHaveBeenCalled()
  })

  it("runs the SSR initial-user and initializing branches", () => {
    const originalWindow = globalThis.window
    vi.stubGlobal("window", undefined)

    const Probe = ({ hint }: { hint?: SsrAuthHint }) => {
      const state = useProfileSync(
        vi.fn(),
        { current: null },
        { current: null },
        vi.fn(async () => null),
        hint
      )
      return (
        <output>{`${state.user?.id ?? "none"}:${state.user?.role ?? "none"}:${state.loading}`}</output>
      )
    }

    try {
      const authenticatedHtml = renderToString(
        <QueryClientProvider client={createQueryClient()}>
          <Probe hint={{ isAuth: true, user: { role: "student" } }} />
        </QueryClientProvider>
      )
      const anonymousHtml = renderToString(
        <QueryClientProvider client={createQueryClient()}>
          <Probe />
        </QueryClientProvider>
      )

      expect(authenticatedHtml).toContain("ssr-stub:student:false")
      expect(anonymousHtml).toContain("none:none:true")

      const invalidRoleHtml = renderToString(
        <QueryClientProvider client={createQueryClient()}>
          <Probe hint={{ isAuth: true, user: { role: "not-a-real-role" } }} />
        </QueryClientProvider>
      )
      expect(invalidRoleHtml).toContain("ssr-stub:student:false")
    } finally {
      vi.stubGlobal("window", originalWindow)
    }
  })

  it("skips browser-only synchronization effects during server runtime", async () => {
    const originalWindow = globalThis.window
    vi.stubGlobal("window", { event: undefined, document: globalThis.document })
    vi.stubEnv("VITE_LHCI", "true")

    try {
      const view = renderRuntime(
        vi.fn(async () => null),
        null
      )

      await waitFor(() => expect(view.result.current.user?.id).toBe("lhci-mock-user"))

      await act(async () => {
        view.result.current.updatePendingMfa({
          ticket: "ssr-ticket",
          methods: [],
        } as never)
      })
      expect(view.result.current.pendingMfa).toMatchObject({ ticket: "ssr-ticket" })
    } finally {
      vi.stubGlobal("window", originalWindow)
    }
  })
})
