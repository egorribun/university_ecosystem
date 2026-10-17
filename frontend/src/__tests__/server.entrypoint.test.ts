/**
 * @vitest-environment node
 */
import { afterAll, beforeEach, describe, expect, it, vi } from "vitest"
import type { RequestOptions } from "@tanstack/react-start/server"
import type { i18n as I18nInstance } from "i18next"

type TestServerRegister = {
  server: { requestContext: { requestId: string } }
}
type TestRequestOptions = RequestOptions<TestServerRegister>
type ServerHandlerResult = Response | Promise<Response>

const mocks = vi.hoisted(() => ({
  handlerFetch: vi.fn<(request: Request, options?: TestRequestOptions) => ServerHandlerResult>(),
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
  __ssrNonceGetter__?: () => string | undefined
  __ssrOriginGetter__?: () => string | undefined
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
  delete globals.__ssrNonceGetter__
  delete globals.__ssrOriginGetter__
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
      expect(globals.__ssrOriginGetter__?.()).toBe("https://app.example")
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
    expect(globals.__ssrOriginGetter__?.()).toBeUndefined()
  })

  it("keeps the generated static shell's theme asset URL relative", async () => {
    const originalPrerendering = process.env.TSS_PRERENDERING
    process.env.TSS_PRERENDERING = "true"
    try {
      mocks.handlerFetch.mockImplementation(async () => {
        expect(globals.__ssrOriginGetter__?.()).toBeUndefined()
        return new Response("shell")
      })

      await serverEntry.fetch(new Request("http://localhost:3000/"))
    } finally {
      if (originalPrerendering === undefined) {
        delete process.env.TSS_PRERENDERING
      } else {
        process.env.TSS_PRERENDERING = originalPrerendering
      }
    }
  })

  it("preserves Start request options and caller context while replacing the nonce", async () => {
    const onEarlyHints = vi.fn()
    const requestOptions = {
      onEarlyHints,
      responseLinkHeader: false,
      inlineCss: false,
      context: {
        nonce: "caller-option-nonce",
        requestId: "caller-context",
      },
    }
    mocks.handlerFetch.mockImplementation(async (_request, forwardedOptions) => {
      expect(forwardedOptions?.context?.nonce).toBe(globals.__ssrNonceGetter__?.())
      return new Response("public")
    })

    const request = new Request("https://app.example/news", {
      headers: { "x-csp-nonce": "caller-header-nonce" },
    })
    await serverEntry.fetch(request, requestOptions)

    const forwardedOptions = mocks.handlerFetch.mock.calls[0]?.[1]
    expect(forwardedOptions?.inlineCss).toBe(false)
    expect(forwardedOptions?.responseLinkHeader).toBe(false)
    expect(forwardedOptions?.onEarlyHints).toBe(onEarlyHints)
    expect(forwardedOptions?.context?.nonce).toBeDefined()
    expect(forwardedOptions?.context?.nonce).not.toBe("caller-option-nonce")
    expect(forwardedOptions?.context?.nonce).not.toBe("caller-header-nonce")
    expect(Reflect.get(forwardedOptions?.context ?? {}, "requestId")).toBe("caller-context")
    expect(globals.__ssrNonceGetter__?.()).toBeUndefined()
  })

  it("keeps concurrent HTML CSP nonces paired per response", async () => {
    const firstPath = "/overlap-first"
    const secondPath = "/overlap-second"
    const noncesByPath = new Map<string, string>()
    let releaseFirst!: (response: Response) => void
    let releaseSecond!: (response: Response) => void
    let resolveBothEntered!: () => void
    let rejectBothEntered!: (reason: unknown) => void
    const firstBody = new Promise<Response>((resolve) => {
      releaseFirst = resolve
    })
    const secondBody = new Promise<Response>((resolve) => {
      releaseSecond = resolve
    })
    const bothEntered = new Promise<void>((resolve, reject) => {
      resolveBothEntered = resolve
      rejectBothEntered = reject
    })

    mocks.handlerFetch.mockImplementation(async (request) => {
      const requestPath = new URL(request.url).pathname
      const nonce = globals.__ssrNonceGetter__?.()
      if (requestPath !== firstPath && requestPath !== secondPath) {
        throw new Error("Unexpected path in concurrent nonce test")
      }
      if (!nonce) {
        throw new Error("Request-scoped nonce unavailable")
      }
      noncesByPath.set(requestPath, nonce)
      if (noncesByPath.size === 2) resolveBothEntered()
      return requestPath === firstPath ? firstBody : secondBody
    })

    const observeFailure = (result: ServerHandlerResult): Promise<Response> =>
      Promise.resolve(result).catch((error: unknown) => {
        rejectBothEntered(error)
        throw error
      })
    const firstRequest = observeFailure(
      serverEntry.fetch(new Request("https://app.example" + firstPath))
    )
    const secondRequest = observeFailure(
      serverEntry.fetch(new Request("https://app.example" + secondPath))
    )
    const pendingResponses = Promise.all([firstRequest, secondRequest])

    try {
      await Promise.race([
        bothEntered,
        pendingResponses.then(() => {
          throw new Error("Controlled handler returned before release")
        }),
      ])

      const firstNonce = noncesByPath.get(firstPath)
      const secondNonce = noncesByPath.get(secondPath)
      expect(firstNonce).toBeDefined()
      expect(secondNonce).toBeDefined()
      if (firstNonce === undefined || secondNonce === undefined) {
        throw new Error("Both request-scoped nonces must be captured")
      }
      expect(firstNonce).not.toBe(secondNonce)

      const firstMarkup =
        '<script nonce="' + firstNonce + '">trustedFirst()</script><script>rawFirst()</script>'
      const secondMarkup =
        '<script nonce="' + secondNonce + '">trustedSecond()</script><script>rawSecond()</script>'
      const htmlHeaders = { "content-type": "text/html; charset=utf-8" }

      releaseSecond(new Response(secondMarkup, { headers: htmlHeaders }))
      releaseFirst(new Response(firstMarkup, { headers: htmlHeaders }))
      const [firstResponse, secondResponse] = await pendingResponses
      const firstPolicy = firstResponse.headers.get("content-security-policy")
      const secondPolicy = secondResponse.headers.get("content-security-policy")
      const firstHeaderNonce = firstPolicy?.match(/'nonce-([^']+)'/u)?.[1]
      const secondHeaderNonce = secondPolicy?.match(/'nonce-([^']+)'/u)?.[1]

      expect(firstHeaderNonce).toBe(firstNonce)
      expect(secondHeaderNonce).toBe(secondNonce)
      expect(firstHeaderNonce).not.toBe(secondHeaderNonce)
      expect(firstResponse.headers.get("cache-control")).toBe("no-store, private, max-age=0")
      expect(secondResponse.headers.get("cache-control")).toBe("no-store, private, max-age=0")
      await expect(firstResponse.text()).resolves.toBe(firstMarkup)
      await expect(secondResponse.text()).resolves.toBe(secondMarkup)
      expect(firstMarkup).toContain(`<script nonce="${firstHeaderNonce}">`)
      expect(secondMarkup).toContain(`<script nonce="${secondHeaderNonce}">`)
      expect(firstMarkup).toContain("<script>rawFirst()</script>")
      expect(secondMarkup).toContain("<script>rawSecond()</script>")
    } finally {
      releaseFirst(new Response("drained"))
      releaseSecond(new Response("drained"))
    }
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

  it("secures public HTML while preserving its status, body, and Vary", async () => {
    const upstream = new Response("public page", {
      status: 203,
      statusText: "Non-Authoritative Information",
      headers: {
        "cache-control": "public, max-age=60",
        "content-type": "text/html; charset=utf-8",
        vary: "Accept-Encoding",
        etag: '"public-v1"',
        "last-modified": "Mon, 01 Jan 2024 00:00:00 GMT",
      },
    })
    mocks.handlerFetch.mockResolvedValue(upstream)

    const response = await serverEntry.fetch(new Request("https://app.example/news"))

    expect(response).not.toBe(upstream)
    expect(response.status).toBe(203)
    expect(response.statusText).toBe("Non-Authoritative Information")
    expect(response.headers.get("cache-control")).toBe("no-store, private, max-age=0")
    expect(response.headers.get("vary")).toBe("Accept-Encoding")
    const policy = response.headers.get("content-security-policy")
    const nonce = policy?.match(/script-src[^;]*'nonce-([^']+)'/u)?.[1]
    expect(nonce).toBeTruthy()
    expect(response.headers.get("content-security-policy-report-only")).toContain(
      `'nonce-${nonce}'`
    )
    expect(response.headers.has("etag")).toBe(false)
    expect(response.headers.has("last-modified")).toBe(false)
    await expect(response.text()).resolves.toBe("public page")
  })

  it("preserves unauthenticated public non-HTML response identity and headers", async () => {
    const upstream = new Response('{"status":"ok"}', {
      status: 202,
      statusText: "Accepted",
      headers: {
        "cache-control": "public, max-age=60",
        "content-type": "application/json; charset=utf-8",
        vary: "Accept-Encoding",
        etag: '"health-v1"',
      },
    })
    mocks.handlerFetch.mockResolvedValue(upstream)

    const response = await serverEntry.fetch(new Request("https://app.example/public-data"))

    expect(response).toBe(upstream)
    expect(response.status).toBe(202)
    expect(response.statusText).toBe("Accepted")
    expect(response.headers.get("cache-control")).toBe("public, max-age=60")
    expect(response.headers.get("content-type")).toBe("application/json; charset=utf-8")
    expect(response.headers.get("vary")).toBe("Accept-Encoding")
    expect(response.headers.get("etag")).toBe('"health-v1"')
    expect(response.headers.has("content-security-policy")).toBe(false)
    expect(response.headers.has("content-security-policy-report-only")).toBe(false)
    await expect(response.text()).resolves.toBe('{"status":"ok"}')
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
