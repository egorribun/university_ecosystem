import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const productionDescribe = describe.skipIf(import.meta.env.MODE !== "production")

productionDescribe("api/client — production CSRF bootstrap", () => {
  beforeEach(() => {
    vi.resetModules()
    document.cookie = "csrf_token=; Max-Age=0; path=/"
  })

  afterEach(() => {
    document.cookie = "csrf_token=; Max-Age=0; path=/"
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it("does not fetch when the browser already has a CSRF cookie", async () => {
    document.cookie = "csrf_token=existing-token; path=/"
    const fetchSpy = vi.fn()
    vi.stubGlobal("fetch", fetchSpy)

    const { ensureCsrfCookie } = await import("@/api/client")

    await expect(ensureCsrfCookie()).resolves.toBeUndefined()
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it("deduplicates concurrent bootstrap calls and clears the singleton after success", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal("fetch", fetchSpy)
    const { ensureCsrfCookie } = await import("@/api/client")

    const first = ensureCsrfCookie()
    const second = ensureCsrfCookie()
    await expect(Promise.all([first, second])).resolves.toEqual([undefined, undefined])

    expect(fetchSpy).toHaveBeenCalledOnce()
    expect(fetchSpy).toHaveBeenCalledWith("/api/v1/auth/csrf-cookie", {
      method: "GET",
      credentials: "include",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })

    await ensureCsrfCookie()
    expect(fetchSpy).toHaveBeenCalledTimes(2)
  })

  it("swallows a bootstrap failure so the unsafe request can report the backend error", async () => {
    const fetchSpy = vi.fn().mockRejectedValue(new Error("network unavailable"))
    vi.stubGlobal("fetch", fetchSpy)
    const { ensureCsrfCookie } = await import("@/api/client")

    await expect(ensureCsrfCookie()).resolves.toBeUndefined()
    expect(fetchSpy).toHaveBeenCalledOnce()
  })
})
