import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("web-vitals", () => ({
  onCLS: vi.fn(),
  onFCP: vi.fn(),
  onINP: vi.fn(),
  onLCP: vi.fn(),
  onTTFB: vi.fn(),
}))
vi.mock("@/app/logger", () => ({ logDebug: vi.fn() }))

import { onFCP, onLCP } from "web-vitals"
import {
  buildTrustedEnvelopeBody,
  initWebVitals,
  isTrustedEnvelopeFresh,
  parseTrustedEnvelope,
  resetWebVitalsForTesting,
} from "@/app/webVitals"

const env: ImportMetaEnv & {
  VITE_ENABLE_WEB_VITALS: string
  VITE_CWV_TRUSTED_RUM: string
  VITE_WEB_VITALS_ENDPOINT: string
} = {
  DEV: false,
  MODE: "production",
  VITE_ENABLE_WEB_VITALS: "true",
  VITE_CWV_TRUSTED_RUM: "true",
  VITE_WEB_VITALS_ENDPOINT: "/api/v1/cwv",
} as ImportMetaEnv & {
  VITE_ENABLE_WEB_VITALS: string
  VITE_CWV_TRUSTED_RUM: string
  VITE_WEB_VITALS_ENDPOINT: string
}

describe("trusted field CWV transport", () => {
  beforeEach(() => {
    window.history.replaceState({}, "", "/")
    resetWebVitalsForTesting()
    vi.clearAllMocks()
    vi.spyOn(window, "matchMedia").mockReturnValue({ matches: true } as MediaQueryList)
  })

  afterEach(() => {
    document.cookie = "csrf_token=; Max-Age=0; path=/"
    vi.useRealTimers()
    resetWebVitalsForTesting()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it("requests a navigation-bound envelope and sends only final certification fields", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            envelope: "signed-envelope",
            expires_at: new Date(Date.now() + 300_000).toISOString(),
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      )
      .mockResolvedValueOnce(new Response(null, { status: 202 }))
    vi.stubGlobal("fetch", fetchMock)

    expect(initWebVitals(env)).toBe(true)
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/v1/cwv/envelope",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: expect.any(String),
      })
    )
    const envelopeBody = JSON.parse(fetchMock.mock.calls[0]![1]!.body as string)
    expect(envelopeBody).toEqual({
      pathname: window.location.pathname,
      device_class: "mobile",
    })

    const reporter = vi.mocked(onLCP).mock.calls[0]![0]
    reporter({ name: "LCP", value: 2400, id: "browser-id-containing-no-trust" } as never)
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    const observationBody = JSON.parse(fetchMock.mock.calls[1]![1]!.body as string)
    expect(observationBody).toEqual({
      envelope: "signed-envelope",
      metric: "LCP",
      value: 2400,
    })
    expect(JSON.stringify(observationBody)).not.toContain("browser-id")
    expect(JSON.stringify(observationBody)).not.toMatch(/email|user_agent|ip_address/i)
    expect(fetchMock.mock.calls[1]![0]).toBe("/api/v1/cwv/observations")
    expect(fetchMock.mock.calls[1]![1]).toEqual(
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        keepalive: true,
        headers: expect.objectContaining({ "Content-Type": "application/json" }),
      })
    )
  })

  it("never submits non-certification metrics and absorbs envelope failure", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error("offline"))
    vi.stubGlobal("fetch", fetchMock)
    expect(initWebVitals(env)).toBe(true)
    vi.mocked(onFCP).mock.calls[0]![0]({ name: "FCP", value: 1000 } as never)
    await Promise.resolve()
    await Promise.resolve()
    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it("filters non-certification metrics after a valid envelope is available", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            envelope: "signed-envelope",
            expires_at: new Date(Date.now() + 300_000).toISOString(),
          }),
          { status: 200 }
        )
      )
      .mockResolvedValue(new Response(null, { status: 202 }))
    vi.stubGlobal("fetch", fetchMock)
    expect(initWebVitals(env)).toBe(true)
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledOnce())

    vi.mocked(onFCP).mock.calls[0]![0]({ name: "FCP", value: 1000 } as never)
    await new Promise((resolve) => window.setTimeout(resolve, 0))
    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it("fails closed when trusted mode has no same-origin endpoint", () => {
    expect(initWebVitals({ ...env, VITE_WEB_VITALS_ENDPOINT: undefined } as never)).toBe(false)
  })

  it("atomically rotates an expiring envelope before submitting a late metric", async () => {
    vi.useFakeTimers()
    const firstExpiry = new Date(Date.now() + 300_000).toISOString()
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ envelope: "first-envelope", expires_at: firstExpiry }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            envelope: "rotated-envelope",
            expires_at: new Date(Date.now() + 600_000).toISOString(),
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      )
      .mockResolvedValue(new Response(null, { status: 202 }))
    vi.stubGlobal("fetch", fetchMock)

    expect(initWebVitals(env)).toBe(true)
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledOnce())
    await vi.advanceTimersByTimeAsync(300_000)
    const reporter = vi.mocked(onLCP).mock.calls[0]![0]
    reporter({ name: "LCP", value: 2300 } as never)
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))

    const renewal = JSON.parse(fetchMock.mock.calls[1]![1]!.body as string)
    expect(renewal.renewal_envelope).toBe("first-envelope")
    const observation = JSON.parse(fetchMock.mock.calls[2]![1]!.body as string)
    expect(observation.envelope).toBe("rotated-envelope")
  })

  it("keeps document-lifecycle metrics bound to the initial SPA route", async () => {
    vi.useFakeTimers()
    const expiresAt = new Date(Date.now() + 300_000).toISOString()
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ envelope: "dashboard-envelope", expires_at: expiresAt }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            envelope: "renewed-dashboard-envelope",
            expires_at: new Date(Date.now() + 600_000).toISOString(),
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      )
      .mockResolvedValueOnce(new Response(null, { status: 202 }))
    vi.stubGlobal("fetch", fetchMock)

    window.history.replaceState({}, "", "/dashboard")
    expect(initWebVitals(env)).toBe(true)
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledOnce())
    window.history.pushState({}, "", "/news")
    await vi.advanceTimersByTimeAsync(300_000)
    vi.mocked(onLCP).mock.calls[0]![0]({ name: "LCP", value: 2100 } as never)
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))

    const routeEnvelope = JSON.parse(fetchMock.mock.calls[1]![1]!.body as string)
    expect(routeEnvelope).toEqual({
      pathname: "/dashboard",
      device_class: "mobile",
      renewal_envelope: "dashboard-envelope",
    })
    const observation = JSON.parse(fetchMock.mock.calls[2]![1]!.body as string)
    expect(observation.envelope).toBe("renewed-dashboard-envelope")
  })

  it("decodes a CSRF cookie for trusted requests and omits a malformed cookie", async () => {
    document.cookie = "csrf_token=bound%20token; path=/"
    const fetchMock = vi.fn().mockRejectedValue(new Error("offline"))
    vi.stubGlobal("fetch", fetchMock)

    expect(initWebVitals(env)).toBe(true)
    expect(fetchMock.mock.calls[0]![1]).toEqual(
      expect.objectContaining({
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": "bound token",
        },
      })
    )

    resetWebVitalsForTesting()
    vi.clearAllMocks()
    document.cookie = "csrf_token=%E0%A4%A; path=/"
    expect(initWebVitals(env)).toBe(true)
    expect(fetchMock.mock.calls[0]![1]).toEqual(
      expect.objectContaining({ headers: { "Content-Type": "application/json" } })
    )
  })

  it("trims cookie segments before locating the CSRF token", () => {
    document.cookie = "other=value; path=/"
    document.cookie = "csrf_token=bound%20token; path=/"
    const fetchMock = vi.fn().mockRejectedValue(new Error("offline"))
    vi.stubGlobal("fetch", fetchMock)

    expect(initWebVitals(env)).toBe(true)
    expect(fetchMock.mock.calls[0]![1]).toEqual(
      expect.objectContaining({
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": "bound token",
        },
      })
    )
  })

  it("rejects malformed and cross-origin trusted endpoints before registration", () => {
    expect(initWebVitals({ ...env, VITE_WEB_VITALS_ENDPOINT: "http://[invalid" })).toBe(false)
    expect(initWebVitals({ ...env, VITE_WEB_VITALS_ENDPOINT: "https://metrics.example/v1" })).toBe(
      false
    )
  })

  it("fails closed before touching an unavailable fetch transport", () => {
    vi.stubGlobal("fetch", undefined)
    expect(() =>
      initWebVitals({ ...env, VITE_WEB_VITALS_ENDPOINT: "https://metrics.example/v1" })
    ).not.toThrow()
    expect(initWebVitals({ ...env, VITE_WEB_VITALS_ENDPOINT: "https://metrics.example/v1" })).toBe(
      false
    )
  })

  it("normalizes trailing endpoint slashes for envelope and observation URLs", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error("offline"))
    vi.stubGlobal("fetch", fetchMock)
    expect(initWebVitals({ ...env, VITE_WEB_VITALS_ENDPOINT: "/api/v1/cwv///" })).toBe(true)

    expect(fetchMock.mock.calls[0]![0]).toBe("/api/v1/cwv/envelope")
  })

  it("keeps renewal metadata absent until a real envelope exists", () => {
    expect(buildTrustedEnvelopeBody("/dashboard", "desktop")).toEqual({
      pathname: "/dashboard",
      device_class: "desktop",
    })
    expect(buildTrustedEnvelopeBody("/dashboard", "desktop", "signed")).toEqual({
      pathname: "/dashboard",
      device_class: "desktop",
      renewal_envelope: "signed",
    })
  })

  it("validates trusted envelope payloads and exact expiry boundaries", () => {
    const now = Date.parse("2026-09-01T10:00:00.000Z")
    expect(
      parseTrustedEnvelope({ envelope: "signed", expires_at: "2026-09-01T10:00:01.000Z" }, now)
    ).toEqual({ envelope: "signed", expiresAt: now + 1000 })
    expect(() =>
      parseTrustedEnvelope({ envelope: "signed", expires_at: new Date(now).toISOString() }, now)
    ).toThrow("CWV envelope malformed")
    expect(() => parseTrustedEnvelope({ envelope: "signed", expires_at: 123 }, now)).toThrow(
      "CWV envelope malformed"
    )
  })

  it("reuses a healthy cached envelope for multiple observations", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            envelope: "cached-envelope",
            expires_at: new Date(Date.now() + 300_000).toISOString(),
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      )
      .mockResolvedValue(new Response(null, { status: 202 }))
    vi.stubGlobal("fetch", fetchMock)

    expect(initWebVitals(env)).toBe(true)
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledOnce())
    await new Promise((resolve) => window.setTimeout(resolve, 0))

    vi.mocked(onLCP).mock.calls[0]![0]({ name: "LCP", value: 2000 } as never)
    vi.mocked(onFCP).mock.calls[0]![0]({ name: "INP", value: 100 } as never)

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/v1/cwv/envelope",
      "/api/v1/cwv/observations",
      "/api/v1/cwv/observations",
    ])
  })

  it("renews an envelope exactly at the thirty-second safety boundary", async () => {
    const now = Date.parse("2026-09-01T10:00:00.000Z")
    expect(isTrustedEnvelopeFresh(now + 30_000, now)).toBe(false)
    expect(isTrustedEnvelopeFresh(now + 30_001, now)).toBe(true)
    expect(isTrustedEnvelopeFresh(Number.NaN, now)).toBe(false)
  })

  it("binds a desktop envelope when the initial viewport is wider than mobile", () => {
    vi.mocked(window.matchMedia).mockReturnValue({ matches: false } as MediaQueryList)
    const fetchMock = vi.fn().mockRejectedValue(new Error("offline"))
    vi.stubGlobal("fetch", fetchMock)

    expect(initWebVitals(env)).toBe(true)

    expect(JSON.parse(fetchMock.mock.calls[0]![1]!.body as string)).toEqual({
      pathname: "/",
      device_class: "desktop",
    })
  })

  it.each([
    ["missing envelope", { expires_at: new Date(Date.now() + 300_000).toISOString() }],
    ["non-string expiry", { envelope: "signed", expires_at: 123 }],
    ["invalid expiry", { envelope: "signed", expires_at: "not-a-date" }],
    ["expired envelope", { envelope: "signed", expires_at: "2020-01-01T00:00:00Z" }],
  ])(
    "drops a %s response and requests a fresh envelope for a later metric",
    async (_case, body) => {
      const fetchMock = vi.fn().mockResolvedValue(
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      )
      vi.stubGlobal("fetch", fetchMock)

      expect(initWebVitals(env)).toBe(true)
      await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledOnce())
      await new Promise((resolve) => window.setTimeout(resolve, 0))
      vi.mocked(onLCP).mock.calls[0]![0]({ name: "LCP", value: 2400 } as never)

      await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
      expect(fetchMock.mock.calls.every(([url]) => url === "/api/v1/cwv/envelope")).toBe(true)
    }
  )

  it("deduplicates certification metrics while the envelope request is pending", async () => {
    let resolveEnvelope!: (value: Response) => void
    const pendingEnvelope = new Promise<Response>((resolve) => {
      resolveEnvelope = resolve
    })
    const fetchMock = vi
      .fn()
      .mockReturnValueOnce(pendingEnvelope)
      .mockResolvedValue(new Response(null, { status: 202 }))
    vi.stubGlobal("fetch", fetchMock)

    expect(initWebVitals(env)).toBe(true)
    vi.mocked(onLCP).mock.calls[0]![0]({ name: "LCP", value: 2200 } as never)
    vi.mocked(onFCP).mock.calls[0]![0]({ name: "CLS", value: 0.05 } as never)
    expect(fetchMock).toHaveBeenCalledOnce()

    resolveEnvelope(
      new Response(
        JSON.stringify({
          envelope: "shared-envelope",
          expires_at: new Date(Date.now() + 300_000).toISOString(),
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      )
    )

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))
    expect(fetchMock.mock.calls.filter(([url]) => url === "/api/v1/cwv/envelope")).toHaveLength(1)
  })

  it("retries envelope collection after a non-success response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 503 }))
    vi.stubGlobal("fetch", fetchMock)

    expect(initWebVitals(env)).toBe(true)
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledOnce())
    await new Promise((resolve) => window.setTimeout(resolve, 0))

    vi.mocked(onLCP).mock.calls[0]![0]({ name: "LCP", value: 2400 } as never)

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(fetchMock.mock.calls.every(([url]) => url === "/api/v1/cwv/envelope")).toBe(true)
  })

  it("absorbs an observation transport rejection after a valid envelope", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            envelope: "signed-envelope",
            expires_at: new Date(Date.now() + 300_000).toISOString(),
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      )
      .mockRejectedValueOnce(new Error("observation endpoint offline"))
    vi.stubGlobal("fetch", fetchMock)

    expect(initWebVitals(env)).toBe(true)
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledOnce())
    await Promise.resolve()
    vi.mocked(onLCP).mock.calls[0]![0]({ name: "LCP", value: 2400 } as never)

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    await expect(Promise.resolve()).resolves.toBeUndefined()
  })
})
