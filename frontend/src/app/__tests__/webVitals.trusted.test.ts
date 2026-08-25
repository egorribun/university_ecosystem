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
import { initWebVitals, resetWebVitalsForTesting } from "@/app/webVitals"

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
})
