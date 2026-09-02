/**
 * Wave 175 SW9 — regression tests for W174 SW2 ensureCsrfCookie helper.
 *
 * W174 SW2 added `ensureCsrfCookie()` in frontend/src/api/client.ts to
 * proactively fetch /api/v1/auth/csrf-cookie before unsafe-method
 * requests (POST/PUT/PATCH/DELETE) if the csrf_token cookie is missing
 * or expired. This closes a real user-facing 403 bug where users
 * arriving with no/expired cookie hit "Несоответствие CSRF-токена"
 * with no automatic recovery.
 *
 * Critical invariants tested here (closes W174 §Honesty #4):
 *
 * 1. SSR guard — `typeof document === "undefined"` returns Promise.resolve()
 *    without attempting fetch. Critical because server.ts SSR runtime
 *    forwards cookies via W133 SW1 globalThis.__ssrCookieGetter__;
 *    duplicate client-side bootstrap would be wasteful + would fail
 *    (no document.cookie API in Node).
 *
 * 2. Test-env skip — `import.meta.env.MODE === "test"` returns
 *    Promise.resolve() without fetch. Critical so vitest tests
 *    don't trigger MSW unhandled-request warnings + don't share
 *    singleton-promise state across tests. Vite literal-substitutes
 *    MODE at build time → branch tree-shakes from prod bundle.
 *
 * 3. Cookie-present short-circuit — if document.cookie already
 *    contains "csrf_token=", returns Promise.resolve() without
 *    fetch. Critical to avoid hammering the endpoint on every
 *    POST when cookie is already valid.
 *
 * 4. Singleton dedup — concurrent calls share the same in-flight
 *    Promise. Critical to avoid N concurrent fetches when N
 *    POST requests fire simultaneously after cold load.
 *
 * 5. Error tolerance — fetch rejection doesn't throw or reject;
 *    helper logs nothing + clears singleton via .finally so next
 *    call retries. Best-effort behavior: if cookie fails to set,
 *    the subsequent POST will 403 → user can retry.
 *
 * Bypassing the test-env guard for tests 3-5:
 * vi.stubEnv("MODE", "production") temporarily flips the env so the
 * MODE !== "test" path executes. Restored via vi.unstubAllEnvs in
 * afterEach to avoid leaking state to other tests.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ensureCsrfCookie } from "../client"

describe("W174 SW2 — ensureCsrfCookie SSR + test-env guards", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it("returns immediately when the SSR runtime has no document", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch")
    vi.stubGlobal("document", undefined)

    await expect(ensureCsrfCookie()).resolves.toBeUndefined()

    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it("returns Promise.resolve() in test env without invoking fetch", async () => {
    // Pre-condition: MODE is "test" by default in vitest
    expect(import.meta.env.MODE).toBe("test")

    const fetchSpy = vi.spyOn(globalThis, "fetch")

    // Even without csrf_token cookie, test-env guard short-circuits
    document.cookie = ""
    await ensureCsrfCookie()

    expect(fetchSpy).not.toHaveBeenCalled()
    fetchSpy.mockRestore()
  })

  it("returns immediately for the side-effect-free Lighthouse preview", async () => {
    vi.stubEnv("VITE_LHCI", "true")
    vi.stubEnv("MODE", "production")
    const fetchSpy = vi.spyOn(globalThis, "fetch")

    document.cookie = ""
    await ensureCsrfCookie()

    expect(fetchSpy).not.toHaveBeenCalled()
  })
})

describe("W174 SW2 — ensureCsrfCookie production behavior", () => {
  beforeEach(() => {
    // Bypass test-env guard so we can verify production behavior
    vi.stubEnv("MODE", "production")
    // Clear document.cookie between tests
    document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;"
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    vi.restoreAllMocks()
    document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;"
  })

  it("short-circuits when csrf_token cookie already present", async () => {
    document.cookie = "csrf_token=existing-token-12345; path=/;"
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null))

    await ensureCsrfCookie()

    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it("fetches /api/v1/auth/csrf-cookie when cookie missing", async () => {
    expect(document.cookie).not.toContain("csrf_token=")
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null))

    await ensureCsrfCookie()

    expect(fetchSpy).toHaveBeenCalledTimes(1)
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/v1/auth/csrf-cookie",
      expect.objectContaining({
        method: "GET",
        credentials: "include",
        headers: expect.objectContaining({ "X-Requested-With": "XMLHttpRequest" }),
      })
    )
  })

  it("dedupes concurrent calls via singleton Promise (1 fetch for N parallel calls)", async () => {
    // Use a deferred Promise so we can verify dedup BEFORE resolution.
    // Explicit type cast on the outer binding works around TS control-flow
    // narrowing limitation (TS narrows to null because assignment is
    // inside the Promise executor callback).
    type ResolveFn = (value: Response) => void
    let resolveFetch: ResolveFn = () => {
      throw new Error("resolveFetch not initialized")
    }
    const deferredFetch = new Promise<Response>((resolve) => {
      resolveFetch = resolve
    })
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockReturnValue(deferredFetch)

    // Fire 5 parallel calls BEFORE any resolves
    const promises = [
      ensureCsrfCookie(),
      ensureCsrfCookie(),
      ensureCsrfCookie(),
      ensureCsrfCookie(),
      ensureCsrfCookie(),
    ]

    // All 5 should share the same in-flight Promise → only 1 fetch
    expect(fetchSpy).toHaveBeenCalledTimes(1)

    // Resolve the deferred fetch + wait for all
    resolveFetch(new Response(null))
    await Promise.all(promises)

    expect(fetchSpy).toHaveBeenCalledTimes(1)
  })

  it("tolerates fetch rejection without throwing", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockRejectedValue(new Error("Network unreachable"))

    // Should NOT throw — helper has .catch(() => undefined) per W174 SW2
    await expect(ensureCsrfCookie()).resolves.toBeUndefined()
    expect(fetchSpy).toHaveBeenCalledTimes(1)
  })

  it("clears singleton state after fetch resolves (subsequent calls re-fetch when cookie still missing)", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null))

    await ensureCsrfCookie()
    expect(fetchSpy).toHaveBeenCalledTimes(1)

    // Cookie still missing (mock fetch didn't actually set it) — next call
    // should re-fetch because singleton was cleared via .finally
    await ensureCsrfCookie()
    expect(fetchSpy).toHaveBeenCalledTimes(2)
  })
})
