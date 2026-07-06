import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { AxiosHeaders } from "axios"
import type { AxiosResponse, InternalAxiosRequestConfig } from "axios"

import api, {
  API_UNAUTHORIZED_EVENT,
  ensureCsrfCookie,
  resetEtagCache,
  SKIP_UNAUTHORIZED_HEADER,
} from "@/api/client"
import { registerSigningKeyAccessor } from "@/api/interceptors/etagCache"

type CapturedConfig = InternalAxiosRequestConfig & {
  etagCacheKey?: string
  skipRateLimitQueue?: boolean
}

/**
 * Install a deterministic adapter so requests never reach MSW (and therefore the
 * contract validator). Returns the array of configs the adapter observed.
 */
const installAdapter = (
  respond: (config: InternalAxiosRequestConfig) => Partial<AxiosResponse> = () => ({})
): CapturedConfig[] => {
  const seen: CapturedConfig[] = []
  api.defaults.adapter = async (config): Promise<AxiosResponse> => {
    seen.push(config as CapturedConfig)
    const partial = respond(config)
    return {
      data: partial.data ?? { ok: true },
      status: partial.status ?? 200,
      statusText: partial.statusText ?? "OK",
      headers: partial.headers ?? new AxiosHeaders(),
      config,
      request: {},
    } as AxiosResponse
  }
  return seen
}

beforeEach(() => {
  resetEtagCache()
  registerSigningKeyAccessor(() => "client-test-signing-key-0123456789")
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("api/client — module exports + instance config", () => {
  it("exposes the documented public constants", () => {
    expect(API_UNAUTHORIZED_EVENT).toBe("auth:unauthorized")
    expect(SKIP_UNAUTHORIZED_HEADER).toBe("X-Client-Skip-Unauthorized")
  })

  it("configures the axios instance with credentials + xsrf + json defaults", () => {
    expect(api.defaults.withCredentials).toBe(true)
    expect(api.defaults.xsrfCookieName).toBe("csrf_token")
    expect(api.defaults.xsrfHeaderName).toBe("X-CSRF-Token")
    expect(api.defaults.headers.Accept).toBe("application/json")
  })

  it("the default export is a callable axios instance with verb helpers", () => {
    for (const verb of ["get", "post", "put", "patch", "delete", "request"] as const) {
      expect(typeof api[verb]).toBe("function")
    }
  })
})

describe("api/client — request interceptor: GET pass-through", () => {
  it("issues a GET and runs through the interceptors without mutating data", async () => {
    const seen = installAdapter(() => ({ data: { items: [42] } }))
    const res = await api.get("/news")
    expect(res.status).toBe(200)
    expect(res.data).toEqual({ items: [42] })
    expect(seen).toHaveLength(1)
    expect((seen[0]!.method ?? "").toLowerCase()).toBe("get")
  })

  it("applies the If-None-Match header when an etagCacheKey + cached tag exist", async () => {
    const seen = installAdapter(() => ({
      data: { items: [] },
      headers: AxiosHeaders.from({ etag: '"abc"', "content-type": "application/json" }),
    }))
    // Prime the cache via a first request, then a second should send If-None-Match.
    await api.get("/events", { etagCacheKey: "events:instance" } as never)
    await api.get("/events", { etagCacheKey: "events:instance" } as never)

    expect(seen).toHaveLength(2)
    const secondHeaders = AxiosHeaders.from(seen[1]!.headers)
    expect(secondHeaders.get("if-none-match")).toBe('"abc"')
  })
})

describe("api/client — request interceptor: FormData", () => {
  it("removes the JSON Content-Type so the browser sets the multipart boundary", async () => {
    const seen = installAdapter()
    const fd = new FormData()
    fd.append("file", new Blob(["x"]), "x.txt")
    await api.post("/files/upload", fd, { skipRateLimitQueue: false } as never)

    expect(seen).toHaveLength(1)
    const headers = AxiosHeaders.from(seen[0]!.headers)
    // The interceptor strips the JSON Content-Type so axios can set the
    // multipart boundary itself — the default application/json must NOT survive.
    const contentType = (headers.get("Content-Type") as string | null) ?? ""
    expect(contentType).not.toContain("application/json")
  })
})

describe("api/client — request interceptor: idempotency dedup", () => {
  it("suppresses a duplicate in-flight mutation sharing the same Idempotency-Key", async () => {
    // Synchronously-resolved deferred gate: the `new Promise` executor runs
    // immediately, so `resolveFirst` is genuinely definite-assigned (closure
    // assignment inside the adapter callback is NOT seen by TS control-flow).
    let resolveFirst!: () => void
    const firstGate = new Promise<void>((resolve) => {
      resolveFirst = resolve
    })
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      await firstGate
      return {
        data: { ok: true },
        status: 200,
        statusText: "OK",
        headers: new AxiosHeaders(),
        config,
        request: {},
      } as AxiosResponse
    }

    const headers = { "Idempotency-Key": "dup-key-1" }
    const first = api.post("/events", { a: 1 }, { headers } as never)
    // Second identical mutation while the first is still in flight → cancelled.
    const second = api.post("/events", { a: 1 }, { headers } as never)

    await expect(second).rejects.toMatchObject({ message: expect.stringContaining("Duplicate") })

    resolveFirst()
    await expect(first).resolves.toMatchObject({ status: 200 })
  })
})

describe("api/client — response interceptor: 401 skip-unauthorized", () => {
  it("rejects 401 directly when the skip-unauthorized header is present", async () => {
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      const err = Object.assign(new Error("Unauthorized"), {
        config,
        response: {
          status: 401,
          statusText: "Unauthorized",
          headers: new AxiosHeaders(),
          data: { detail: "no" },
          config,
        },
      })
      throw err
    }

    await expect(
      api.get("/users/me", { headers: { [SKIP_UNAUTHORIZED_HEADER]: "1" } } as never)
    ).rejects.toMatchObject({ response: { status: 401 } })
  })
})

describe("api/client — ensureCsrfCookie", () => {
  it("resolves immediately in the test environment without fetching", async () => {
    const fetchSpy = vi.fn()
    vi.stubGlobal("fetch", fetchSpy)
    await expect(ensureCsrfCookie()).resolves.toBeUndefined()
    // MODE === "test" short-circuit means no network call.
    expect(fetchSpy).not.toHaveBeenCalled()
  })
})

describe("api/client — prefix normalization", () => {
  it("normalizes relative doubled prefix", async () => {
    const seen = installAdapter()
    await api.get("/api/v1/api/v1/news")
    expect(seen).toHaveLength(1)
    expect(seen[0]!.url).toBe("/api/v1/news")
  })

  it("normalizes absolute doubled prefix during SSR", async () => {
    const seen = installAdapter()
    await api.get("http://localhost:8000/api/v1/api/v1/news")
    expect(seen).toHaveLength(1)
    expect(seen[0]!.url).toBe("http://localhost:8000/api/v1/news")
  })

  it("normalizes absolute single prefix if baseURL matches prefix", async () => {
    const seen = installAdapter()
    api.defaults.baseURL = "/api/v1"
    await api.get("http://localhost:8000/api/v1/news")
    expect(seen).toHaveLength(1)
    expect(seen[0]!.url).toBe("http://localhost:8000/news")
    api.defaults.baseURL = ""
  })
})
