/**
 * @vitest-environment node
 */
import { afterAll, beforeEach, describe, expect, it, vi } from "vitest"
import type { i18n as I18nInstance } from "i18next"

const mocks = vi.hoisted(() => ({
  handlerFetch: vi.fn<(request: Request) => Promise<Response>>(),
  createServerEntry: vi.fn(<T>(entry: T): T => entry),
  extractAuthFromRequest: vi.fn(),
  extractThemeFromRequest: vi.fn(),
  extractLangFromRequest: vi.fn(),
  unauthenticated: {
    isAuth: false,
    user: null,
    loading: false,
  } as const,
}))

const unauthenticated = mocks.unauthenticated

vi.mock("@tanstack/react-start/server-entry", () => ({
  default: { fetch: mocks.handlerFetch },
  createServerEntry: mocks.createServerEntry,
}))

vi.mock("../ssrAuth", () => ({
  extractAuthFromRequest: mocks.extractAuthFromRequest,
  SSR_AUTH_UNAUTH: mocks.unauthenticated,
}))

vi.mock("../ssrTheme", () => ({
  extractThemeFromRequest: mocks.extractThemeFromRequest,
  extractLangFromRequest: mocks.extractLangFromRequest,
}))

import serverEntry from "../server"

type ServerGlobals = typeof globalThis & {
  __ssrAuthGetter__?: () => unknown
  __ssrCookieGetter__?: () => string | undefined
  __ssrFingerprintHeadersGetter__?: () => { userAgent: string; acceptLanguage: string } | undefined
  __ssrThemeGetter__?: () => string | undefined
  __ssrLangGetter__?: () => string | undefined
  __ssrI18nGetter__?: () => I18nInstance | undefined
}

const globals = globalThis as ServerGlobals

beforeEach(() => {
  mocks.handlerFetch.mockReset()
  mocks.extractAuthFromRequest.mockReset()
  mocks.extractThemeFromRequest.mockReset()
  mocks.extractLangFromRequest.mockReset()

  mocks.extractAuthFromRequest.mockResolvedValue(unauthenticated)
  mocks.extractThemeFromRequest.mockReturnValue("light")
  mocks.extractLangFromRequest.mockReturnValue("ru")
  mocks.handlerFetch.mockResolvedValue(new Response("upstream"))
})

afterAll(() => {
  delete globals.__ssrAuthGetter__
  delete globals.__ssrCookieGetter__
  delete globals.__ssrFingerprintHeadersGetter__
  delete globals.__ssrThemeGetter__
  delete globals.__ssrLangGetter__
  delete globals.__ssrI18nGetter__
})

describe("server entrypoint", () => {
  it("serves the health probe without invoking authentication or SSR", async () => {
    const response = await serverEntry.fetch(new Request("https://app.example/healthz"))

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual({ status: "ok" })
    expect(response.headers.get("content-type")).toBe("application/json; charset=utf-8")
    expect(response.headers.get("cache-control")).toBe("no-store")
    expect(mocks.extractAuthFromRequest).not.toHaveBeenCalled()
    expect(mocks.handlerFetch).not.toHaveBeenCalled()
  })

  it("scopes auth, cookies, fingerprint headers, theme, and language to a regular SSR request", async () => {
    const auth = {
      isAuth: true,
      user: { role: "admin" },
      loading: false,
    }
    const upstream = new Response("dashboard", { status: 201 })
    mocks.extractAuthFromRequest.mockResolvedValue(auth)
    mocks.extractThemeFromRequest.mockReturnValue("dark")
    mocks.extractLangFromRequest.mockReturnValue("en")
    mocks.handlerFetch.mockImplementation(async () => {
      expect(globals.__ssrAuthGetter__?.()).toEqual(auth)
      expect(globals.__ssrCookieGetter__?.()).toBe("access_token_v2=opaque; ue-mode=dark")
      expect(globals.__ssrFingerprintHeadersGetter__?.()).toEqual({
        userAgent: "Browser/123",
        acceptLanguage: "en-GB,en;q=0.9",
      })
      expect(globals.__ssrThemeGetter__?.()).toBe("dark")
      expect(globals.__ssrLangGetter__?.()).toBe("en")
      expect(globals.__ssrI18nGetter__?.()?.t("navigation:brandName")).toBe("GUU Ecosystem")
      return upstream
    })

    const request = new Request("https://app.example/dashboard", {
      headers: {
        cookie: "access_token_v2=opaque; ue-mode=dark",
        "user-agent": "Browser/123",
        "accept-language": "en-GB,en;q=0.9",
      },
    })
    const response = await serverEntry.fetch(request)

    expect(response.status).toBe(201)
    await expect(response.text()).resolves.toBe("dashboard")
    expect(mocks.extractThemeFromRequest).toHaveBeenCalledWith(request)
    expect(mocks.extractLangFromRequest).toHaveBeenCalledWith(request)
    expect(globals.__ssrAuthGetter__?.()).toBeUndefined()
    expect(globals.__ssrCookieGetter__?.()).toBeUndefined()
    expect(globals.__ssrFingerprintHeadersGetter__?.()).toBeUndefined()
    expect(globals.__ssrThemeGetter__?.()).toBeUndefined()
    expect(globals.__ssrLangGetter__?.()).toBeUndefined()
    expect(globals.__ssrI18nGetter__?.()).toBeUndefined()
  })

  it("falls back to unauthenticated state and an empty cookie on extraction failure", async () => {
    mocks.extractAuthFromRequest.mockRejectedValue(new Error("jwks unavailable"))
    mocks.handlerFetch.mockImplementation(async () => {
      expect(globals.__ssrAuthGetter__?.()).toBe(unauthenticated)
      expect(globals.__ssrCookieGetter__?.()).toBe("")
      return new Response("public")
    })

    const response = await serverEntry.fetch(new Request("https://app.example/news"))

    await expect(response.text()).resolves.toBe("public")
  })

  it.each(["/dashboard", "/settings/security"])(
    "marks authenticated SSR route %s private and preserves its response",
    async (path) => {
      mocks.extractAuthFromRequest.mockResolvedValue({
        isAuth: true,
        user: { role: "student" },
        loading: false,
      })
      const upstream = new Response("private dashboard payload", {
        status: 203,
        statusText: "Non-Authoritative Information",
        headers: {
          "cache-control": "public, max-age=600",
          "content-type": "text/html; charset=utf-8",
          vary: "Accept-Encoding, Origin",
        },
      })
      mocks.handlerFetch.mockResolvedValue(upstream)

      const response = await serverEntry.fetch(new Request(`https://app.example${path}`))

      expect(response.status).toBe(203)
      expect(response.statusText).toBe("Non-Authoritative Information")
      expect(response.headers.get("cache-control")).toBe("no-store, private, max-age=0")
      expect(response.headers.get("vary")).toBe("Accept-Encoding, Origin, Cookie")
      expect(response.headers.get("content-type")).toBe("text/html; charset=utf-8")
      await expect(response.text()).resolves.toBe("private dashboard payload")
    }
  )

  it("leaves unauthenticated public response headers and identity unchanged", async () => {
    const upstream = new Response("public page", {
      headers: {
        "cache-control": "public, max-age=60",
        "content-type": "text/html; charset=utf-8",
        vary: "Accept-Encoding",
      },
    })
    mocks.handlerFetch.mockResolvedValue(upstream)

    const response = await serverEntry.fetch(new Request("https://app.example/news"))

    expect(response).toBe(upstream)
    expect(response.headers.get("cache-control")).toBe("public, max-age=60")
    expect(response.headers.get("vary")).toBe("Accept-Encoding")
    await expect(response.text()).resolves.toBe("public page")
  })
  it("adds private cache headers and Cookie variance to messenger responses", async () => {
    mocks.handlerFetch.mockResolvedValue(
      new Response("chat", {
        status: 202,
        statusText: "Accepted",
        headers: {
          "content-type": "text/plain",
          vary: "Accept-Encoding, , Origin",
        },
      })
    )

    const response = await serverEntry.fetch(new Request("https://app.example/messenger/room-1"))

    expect(response.status).toBe(202)
    expect(response.statusText).toBe("Accepted")
    expect(response.headers.get("cache-control")).toBe("no-store, private, max-age=0")
    expect(response.headers.get("vary")).toBe("Accept-Encoding, , Origin, Cookie")
    expect(response.headers.get("content-type")).toContain("text/plain")
    await expect(response.text()).resolves.toBe("chat")
  })

  it("does not duplicate an existing case-insensitive Cookie variance token", async () => {
    mocks.handlerFetch.mockResolvedValue(
      new Response("chat", {
        headers: { vary: "Accept-Encoding, cOoKiE" },
      })
    )

    const response = await serverEntry.fetch(new Request("https://app.example/messenger"))

    expect(response.headers.get("vary")).toBe("Accept-Encoding, cOoKiE")
    expect(response.headers.get("cache-control")).toBe("no-store, private, max-age=0")
  })

  it("preserves an existing wildcard Vary value without appending Cookie", async () => {
    mocks.handlerFetch.mockResolvedValue(
      new Response("chat", {
        headers: { vary: "*" },
      })
    )

    const response = await serverEntry.fetch(new Request("https://app.example/messenger"))

    expect(response.headers.get("vary")).toBe("*")
    expect(response.headers.get("cache-control")).toBe("no-store, private, max-age=0")
  })

  it("creates Cookie variance when the upstream response has no Vary header", async () => {
    mocks.handlerFetch.mockResolvedValue(new Response("chat"))

    const response = await serverEntry.fetch(new Request("https://app.example/messenger"))

    expect(response.headers.get("vary")).toBe("Cookie")
  })
})
