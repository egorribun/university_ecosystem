import type { MutableRefObject, PropsWithChildren } from "react"
import { renderHook, waitFor, cleanup } from "@testing-library/react"
import { renderToString } from "react-dom/server"
import { QueryClientProvider } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"

import api from "@/api/client"
import { createQueryClient } from "@/app/queryClient"
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
  initialSigningKey: string | null = signingKey
) => {
  const queryClient = createQueryClient()
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
  it("uses the LHCI user without fetching the profile", async () => {
    vi.stubEnv("VITE_LHCI", "true")
    const getSpy = vi.spyOn(api, "get")

    const { result } = renderRuntime(
      vi.fn(async () => null),
      null
    )

    await waitFor(() => expect(result.current.user?.id).toBe("lhci-mock-user"))
    expect(result.current.loading).toBe(false)
    expect(getSpy).not.toHaveBeenCalled()
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
      return <output>{`${state.user?.id ?? "none"}:${state.loading}`}</output>
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

      expect(authenticatedHtml).toContain("ssr-stub:false")
      expect(anonymousHtml).toContain("none:true")
    } finally {
      vi.stubGlobal("window", originalWindow)
    }
  })
})
