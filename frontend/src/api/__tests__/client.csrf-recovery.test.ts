import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { AxiosError, AxiosHeaders, isCancel } from "axios"
import type { AxiosResponse, InternalAxiosRequestConfig } from "axios"
import { http, HttpResponse } from "msw"

import { server } from "@/tests/mocks/server"
import type { ApiRequestConfig } from "@/api/client"

type Client = (typeof import("@/api/client"))["default"]
const SESSION_GENERATION_KEY = "ecosystem.session.generation.v1"

const responseFor = (config: InternalAxiosRequestConfig): AxiosResponse => ({
  config,
  status: 200,
  statusText: "OK",
  headers: new AxiosHeaders(),
  data: { ok: true },
})

const rejection = (
  client: Client,
  config: InternalAxiosRequestConfig,
  { marker = "1", responseUrl }: { marker?: string; responseUrl?: string } = {}
) => {
  const request = {
    responseURL: responseUrl ?? new URL(client.getUri(config), location.origin).href,
  }
  const response: AxiosResponse = {
    config,
    status: 403,
    statusText: "Forbidden",
    headers: AxiosHeaders.from({ "X-CSRF-Rejected": marker }),
    data: { detail: "Forbidden" },
    request,
  }
  return new AxiosError("Forbidden", "ERR_BAD_REQUEST", config, request, response)
}

beforeEach(() => {
  vi.resetModules()
  vi.stubEnv("MODE", "production")
  vi.stubEnv("VITE_LHCI", "false")
  localStorage.removeItem(SESSION_GENERATION_KEY)
  document.cookie = "csrf_token=old-session-proof; path=/"
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  vi.useRealTimers()
  localStorage.removeItem(SESSION_GENERATION_KEY)
  document.cookie = "csrf_token=; Max-Age=0; path=/"
})

describe("marked CSRF recovery", () => {
  it("uses the real Axios XHR adapter to refresh and replay a JSON mutation once", async () => {
    const proofs: Array<string | null> = []
    const keys: Array<string | null> = []
    const bodies: unknown[] = []
    server.use(
      http.post("*/api/v1/csrf-recovery-test", async ({ request }) => {
        proofs.push(request.headers.get("x-csrf-token"))
        keys.push(request.headers.get("idempotency-key"))
        bodies.push(await request.json())
        return proofs.length === 1
          ? HttpResponse.json({}, { status: 403, headers: { "X-CSRF-Rejected": "1" } })
          : HttpResponse.json({ ok: true })
      })
    )
    const fetchSpy = vi.fn(async () => {
      document.cookie = "csrf_token=new-session-proof; path=/"
      return new Response(null, { status: 204 })
    })
    vi.stubGlobal("fetch", fetchSpy)
    const { default: client } = await import("@/api/client")
    const result = await client.post(
      "/api/v1/csrf-recovery-test",
      { title: "same payload" },
      { headers: { "Idempotency-Key": "csrf-operation-key" } }
    )

    expect(result.status).toBe(200)
    expect(proofs).toEqual(["old-session-proof", "new-session-proof"])
    expect(keys).toEqual(["csrf-operation-key", "csrf-operation-key"])
    expect(bodies).toEqual([{ title: "same payload" }, { title: "same payload" }])
    expect(fetchSpy).toHaveBeenCalledExactlyOnceWith(
      "/api/v1/auth/csrf-cookie",
      expect.objectContaining({
        method: "GET",
        mode: "same-origin",
        credentials: "include",
        cache: "no-store",
        redirect: "error",
      })
    )
  })

  it("retains the idempotency reservation through refresh and the retry", async () => {
    let receiveDedupe: ((event: MessageEvent) => void) | undefined
    class DedupeChannel {
      addEventListener(_type: string, listener: (event: MessageEvent) => void) {
        receiveDedupe = listener
      }
      postMessage() {}
    }
    vi.stubGlobal("BroadcastChannel", DedupeChannel)
    let finishRefresh!: (response: Response) => void
    const refresh = new Promise<Response>((resolve) => {
      finishRefresh = resolve
    })
    const fetchSpy = vi.fn(() => refresh)
    vi.stubGlobal("fetch", fetchSpy)
    const { default: client } = await import("@/api/client")
    let finishRetry!: () => void
    let calls = 0
    client.defaults.adapter = async (config) => {
      calls += 1
      if (calls === 1) throw rejection(client, config)
      if (calls === 2)
        return new Promise((resolve) => {
          finishRetry = () => resolve(responseFor(config))
        })
      return responseFor(config)
    }
    const options = { headers: { "Idempotency-Key": "retained-operation-key" } }
    const first = client.post("/api/v1/events", { title: "one" }, options)
    await vi.waitFor(() => expect(fetchSpy).toHaveBeenCalledOnce())
    if (!receiveDedupe) throw new Error("The cross-tab dedupe listener was not installed")
    receiveDedupe({ data: { key: "retained-operation-key", action: "delete" } } as MessageEvent)
    const duplicateDuringRefresh = await client
      .post("/api/v1/events", { title: "one" }, options)
      .catch((error: unknown) => error)
    expect(isCancel(duplicateDuringRefresh)).toBe(true)
    expect(calls).toBe(1)
    finishRefresh(new Response(null, { status: 204 }))
    await vi.waitFor(() => expect(calls).toBe(2))
    const duplicateDuringRetry = await client
      .post("/api/v1/events", { title: "one" }, options)
      .catch((error: unknown) => error)
    expect(isCancel(duplicateDuringRetry)).toBe(true)
    finishRetry()
    await expect(first).resolves.toMatchObject({ status: 200 })
    await expect(client.post("/api/v1/events", { title: "one" }, options)).resolves.toMatchObject({
      status: 200,
    })
    expect(calls).toBe(3)
  })

  it("replays the same FormData and file when the caller mutates its original form", async () => {
    const fetchSpy = vi.fn(async () => new Response(null, { status: 204 }))
    vi.stubGlobal("fetch", fetchSpy)
    const { default: client } = await import("@/api/client")
    const original = new FormData()
    const file = new File(["file contents"], "proof.txt", { type: "text/plain" })
    original.append("caption", "first")
    original.append("file", file)
    const captured: FormData[] = []
    client.defaults.adapter = async (config) => {
      captured.push(config.data as FormData)
      if (captured.length === 1) {
        original.set("caption", "changed while pending")
        throw rejection(client, config)
      }
      return responseFor(config)
    }
    await client.post("/api/v1/upload", original, { headers: { "Idempotency-Key": "upload-key" } })
    expect(captured).toHaveLength(2)
    for (const form of captured) {
      expect(form.get("caption")).toBe("first")
      const savedFile = form.get("file")
      expect(savedFile).toBeInstanceOf(File)
      expect(savedFile).toMatchObject({ name: "proof.txt", type: "text/plain", size: 13 })
      const contents = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => resolve(String(reader.result))
        reader.onerror = () => reject(reader.error)
        reader.readAsText(savedFile as File)
      })
      expect(contents).toBe("file contents")
    }
    expect(captured[0]).not.toBe(captured[1])
    expect(fetchSpy).toHaveBeenCalledOnce()
  })

  it("replays a bodyless DELETE after the marked rejection", async () => {
    const fetchSpy = vi.fn(async () => new Response(null, { status: 204 }))
    vi.stubGlobal("fetch", fetchSpy)
    const { default: client } = await import("@/api/client")
    let calls = 0
    client.defaults.adapter = async (config) => {
      calls += 1
      expect(config.data).toBeUndefined()
      if (calls === 1) throw rejection(client, config)
      return responseFor(config)
    }
    await expect(client.delete("/api/v1/events/event-id")).resolves.toMatchObject({ status: 200 })
    expect(calls).toBe(2)
    expect(fetchSpy).toHaveBeenCalledOnce()
  })

  it("replays a default-serialized JSON subtype", async () => {
    const fetchSpy = vi.fn(async () => new Response(null, { status: 204 }))
    vi.stubGlobal("fetch", fetchSpy)
    const { default: client } = await import("@/api/client")
    let calls = 0
    client.defaults.adapter = async (config) => {
      calls += 1
      if (calls === 1) throw rejection(client, config)
      return responseFor(config)
    }
    await expect(
      client.post("/api/v1/events", '{"title":"one"}', {
        headers: { "Content-Type": "application/vnd.example+json; charset=utf-8" },
      })
    ).resolves.toMatchObject({ status: 200 })
    expect(calls).toBe(2)
    expect(fetchSpy).toHaveBeenCalledOnce()
  })

  it("supports Axios's single default request transformer", async () => {
    const fetchSpy = vi.fn(async () => new Response(null, { status: 204 }))
    vi.stubGlobal("fetch", fetchSpy)
    const { default: axios } = await import("axios")
    const original = axios.defaults.transformRequest
    const transformer = Array.isArray(original) ? original[0] : original
    if (!transformer) throw new Error("Axios has no default request transformer")
    try {
      axios.defaults.transformRequest = transformer
      const { default: client } = await import("@/api/client")
      let calls = 0
      client.defaults.adapter = async (config) => {
        calls += 1
        if (calls === 1) throw rejection(client, config)
        return responseFor(config)
      }
      await expect(client.post("/api/v1/events", { title: "one" })).resolves.toMatchObject({
        status: 200,
      })
      expect(calls).toBe(2)
      expect(fetchSpy).toHaveBeenCalledOnce()
    } finally {
      axios.defaults.transformRequest = original
    }
  })

  it("uses the Axios error request URL when the response has no request reference", async () => {
    const fetchSpy = vi.fn(async () => new Response(null, { status: 204 }))
    vi.stubGlobal("fetch", fetchSpy)
    const { default: client } = await import("@/api/client")
    let calls = 0
    client.defaults.adapter = async (config) => {
      calls += 1
      if (calls === 1) {
        const error = rejection(client, config)
        if (!error.response) throw new Error("Missing synthetic response")
        delete error.response.request
        throw error
      }
      return responseFor(config)
    }
    await expect(client.post("/api/v1/events", { title: "one" })).resolves.toMatchObject({
      status: 200,
    })
    expect(calls).toBe(2)
    expect(fetchSpy).toHaveBeenCalledOnce()
  })

  it("replays the normal URL-encoded login without recording form values", async () => {
    const fetchSpy = vi.fn(async () => new Response(null, { status: 204 }))
    vi.stubGlobal("fetch", fetchSpy)
    const { default: client } = await import("@/api/client")
    const form = new URLSearchParams([
      ["username", "synthetic"],
      ["password", "synthetic"],
    ])
    let calls = 0
    client.defaults.adapter = async (config) => {
      calls += 1
      expect(typeof config.data === "string" && config.data === form.toString()).toBe(true)
      if (calls === 1) throw rejection(client, config)
      return responseFor(config)
    }
    await expect(
      client.post("/auth/login", form, {
        baseURL: "/api/v1",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        skipRateLimitQueue: true,
      } as ApiRequestConfig)
    ).resolves.toMatchObject({ status: 200 })
    expect(calls).toBe(2)
    expect(fetchSpy).toHaveBeenCalledOnce()
  })

  it.each([
    ["a different API route", "/api/v1/events", new URLSearchParams({ field: "value" })],
    [
      "a login query alias",
      "/api/v1/auth/login?next=events",
      new URLSearchParams({ field: "value" }),
    ],
    ["a raw login form string", "/api/v1/auth/login", "field=value"],
  ])("does not refresh a serialized form for %s", async (_label, path, body) => {
    const fetchSpy = vi.fn()
    vi.stubGlobal("fetch", fetchSpy)
    const { default: client } = await import("@/api/client")
    let calls = 0
    client.defaults.adapter = async (config) => {
      calls += 1
      throw rejection(client, config)
    }
    await expect(
      client.post(path, body, { headers: { "Content-Type": "application/x-www-form-urlencoded" } })
    ).rejects.toMatchObject({ response: { status: 403 } })
    expect(calls).toBe(1)
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it("replays the exact same-origin WebSocket ticket alias after a marked rejection", async () => {
    const fetchSpy = vi.fn(async () => new Response(null, { status: 204 }))
    vi.stubGlobal("fetch", fetchSpy)
    const { default: client } = await import("@/api/client")
    let calls = 0
    client.defaults.adapter = async (config) => {
      calls += 1
      if (calls === 1) throw rejection(client, config)
      return responseFor(config)
    }
    await expect(client.post("/ws/ticket", undefined, { baseURL: "" })).resolves.toMatchObject({
      status: 200,
    })
    expect(calls).toBe(2)
    expect(fetchSpy).toHaveBeenCalledOnce()
  })

  it.each([
    ["ordinary 403", "", undefined],
    ["ambiguous marker", "1, 1", undefined],
    ["missing final response URL", "1", ""],
    ["foreign final response", "1", "https://foreign.invalid/api/v1/events"],
    ["different same-origin path", "1", `${location.origin}/api/v1/other`],
    ["different same-origin query", "1", `${location.origin}/api/v1/events?other=1`],
  ])("does not refresh for %s", async (_name, marker, responseUrl) => {
    const fetchSpy = vi.fn()
    vi.stubGlobal("fetch", fetchSpy)
    const { default: client } = await import("@/api/client")
    let attempts = 0
    client.defaults.adapter = async (config) => {
      attempts += 1
      throw rejection(client, config, { marker, responseUrl })
    }
    await expect(client.post("/api/v1/events", { title: "one" })).rejects.toMatchObject({
      response: { status: 403 },
    })
    expect(attempts).toBe(1)
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it("does not refresh for a marked response to a foreign request", async () => {
    const fetchSpy = vi.fn()
    vi.stubGlobal("fetch", fetchSpy)
    const { default: client } = await import("@/api/client")
    client.defaults.adapter = async (config) => {
      throw rejection(client, config)
    }
    await expect(
      client.post("https://foreign.invalid/api/v1/events", { title: "one" })
    ).rejects.toMatchObject({ response: { status: 403 } })
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it.each([
    ["the final response", "/api/v1/events", "http://[::1"],
    ["the original request", "http://[", `${location.origin}/api/v1/events`],
  ])("does not refresh when %s has an invalid URL", async (_label, path, responseUrl) => {
    const fetchSpy = vi.fn()
    vi.stubGlobal("fetch", fetchSpy)
    const { default: client } = await import("@/api/client")
    let calls = 0
    client.defaults.adapter = async (config) => {
      calls += 1
      throw rejection(client, config, { responseUrl })
    }
    await expect(client.post(path, { title: "one" })).rejects.toMatchObject({
      response: { status: 403 },
    })
    expect(calls).toBe(1)
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it("does not replay malformed serialized JSON after a marked rejection", async () => {
    const fetchSpy = vi.fn()
    vi.stubGlobal("fetch", fetchSpy)
    const { default: client } = await import("@/api/client")
    let calls = 0
    client.defaults.adapter = async (config) => {
      calls += 1
      throw rejection(client, config)
    }
    await expect(
      client.post("/api/v1/events", "{", {
        headers: { "Content-Type": "application/problem+json" },
      })
    ).rejects.toMatchObject({ response: { status: 403 } })
    expect(calls).toBe(1)
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it.each(["File", "entries"] as const)(
    "does not replay multipart when %s support is unavailable",
    async (missing) => {
      const fetchSpy = vi.fn()
      vi.stubGlobal("fetch", fetchSpy)
      const { default: client } = await import("@/api/client")
      const form = new FormData()
      form.append("caption", "one")
      if (missing === "File") vi.stubGlobal("File", undefined)
      else Object.defineProperty(form, "entries", { value: undefined })
      let calls = 0
      client.defaults.adapter = async (config) => {
        calls += 1
        throw rejection(client, config)
      }
      await expect(client.post("/api/v1/upload", form)).rejects.toMatchObject({
        response: { status: 403 },
      })
      expect(calls).toBe(1)
      expect(fetchSpy).not.toHaveBeenCalled()
    }
  )

  it("does not replay a multipart implementation that yields a non-File blob", async () => {
    const fetchSpy = vi.fn()
    vi.stubGlobal("fetch", fetchSpy)
    const { default: client } = await import("@/api/client")
    const form = new FormData()
    Object.defineProperty(form, "entries", {
      value: function* () {
        yield ["attachment", new Blob(["one"])]
      },
    })
    let calls = 0
    client.defaults.adapter = async (config) => {
      calls += 1
      throw rejection(client, config)
    }
    await expect(client.post("/api/v1/upload", form)).rejects.toMatchObject({
      response: { status: 403 },
    })
    expect(calls).toBe(1)
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it("does not refresh a marked response when the Axios URL is missing", async () => {
    const fetchSpy = vi.fn()
    vi.stubGlobal("fetch", fetchSpy)
    const { default: client } = await import("@/api/client")
    let calls = 0
    client.defaults.adapter = async (config) => {
      calls += 1
      throw rejection(client, config, { responseUrl: `${location.origin}/api/v1/events` })
    }
    await expect(client.request({ method: "post", data: { title: "one" } })).rejects.toMatchObject({
      response: { status: 403 },
    })
    expect(calls).toBe(1)
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it("does not refresh a marked response during server rendering", async () => {
    const fetchSpy = vi.fn()
    vi.stubGlobal("fetch", fetchSpy)
    vi.stubGlobal("window", undefined)
    vi.stubGlobal("document", undefined)
    const { default: client } = await import("@/api/client")
    let calls = 0
    client.defaults.adapter = async (config) => {
      calls += 1
      throw rejection(client, config, { responseUrl: "http://localhost:8000/api/v1/events" })
    }
    await expect(client.post("/api/v1/events", { title: "one" })).rejects.toMatchObject({
      response: { status: 403 },
    })
    expect(calls).toBe(1)
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it("does not replay a body without a string content type", async () => {
    const fetchSpy = vi.fn()
    vi.stubGlobal("fetch", fetchSpy)
    const { default: client } = await import("@/api/client")
    let calls = 0
    client.defaults.adapter = async (config) => {
      calls += 1
      throw rejection(client, config)
    }
    await expect(
      client.post("/api/v1/events", "{}", { headers: { "Content-Type": false } })
    ).rejects.toMatchObject({ response: { status: 403 } })
    expect(calls).toBe(1)
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it("refuses an explicitly redirected response even if its final URL matches", async () => {
    const fetchSpy = vi.fn()
    vi.stubGlobal("fetch", fetchSpy)
    const { default: client } = await import("@/api/client")
    client.defaults.adapter = async (config) => {
      const error = rejection(client, config)
      Object.assign(error.response!, { redirected: true })
      throw error
    }
    await expect(client.post("/api/v1/events", { title: "one" })).rejects.toMatchObject({
      response: { status: 403 },
    })
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it("rejects aliases outside the API and the exact WebSocket ticket path", async () => {
    const fetchSpy = vi.fn()
    vi.stubGlobal("fetch", fetchSpy)
    const { default: client } = await import("@/api/client")
    client.defaults.adapter = async (config) => {
      throw rejection(client, config)
    }
    for (const path of ["/ws/ticket?extra=1", "/ws/ticket/extra", "/other"]) {
      await expect(client.post(path, undefined, { baseURL: "" })).rejects.toMatchObject({
        response: { status: 403 },
      })
    }
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it("retains the same-key reservation through a 429 after CSRF refresh", async () => {
    vi.useFakeTimers()
    const fetchSpy = vi.fn(async () => new Response(null, { status: 204 }))
    vi.stubGlobal("fetch", fetchSpy)
    const { default: client } = await import("@/api/client")
    let calls = 0
    client.defaults.adapter = async (config) => {
      calls += 1
      if (calls === 1) throw rejection(client, config)
      if (calls === 2) {
        const error = rejection(client, config)
        if (!error.response) throw new Error("Missing synthetic rate-limit response")
        error.response.status = 429
        error.response.headers = AxiosHeaders.from({ "Retry-After": "1" })
        throw error
      }
      return responseFor(config)
    }
    const options = { headers: { "Idempotency-Key": "csrf-then-rate-limit" } }
    const first = client.post("/api/v1/events", { title: "one" }, options)
    await vi.waitFor(() => expect(calls).toBe(2))
    const duplicate = await client
      .post("/api/v1/events", { title: "one" }, options)
      .catch((error: unknown) => error)
    expect(isCancel(duplicate)).toBe(true)
    expect(calls).toBe(2)
    await vi.advanceTimersByTimeAsync(1_000)
    await expect(first).resolves.toMatchObject({ status: 200 })
    expect(calls).toBe(3)
    expect(fetchSpy).toHaveBeenCalledOnce()
  })

  it("does not refresh a marked safe read or an unconfirmed network error", async () => {
    const fetchSpy = vi.fn()
    vi.stubGlobal("fetch", fetchSpy)
    const { default: client } = await import("@/api/client")
    let calls = 0
    client.defaults.adapter = async (config) => {
      calls += 1
      if (calls === 1) throw rejection(client, config)
      throw new AxiosError("offline", "ERR_NETWORK", config)
    }
    await expect(client.get("/api/v1/events")).rejects.toMatchObject({ response: { status: 403 } })
    await expect(client.post("/api/v1/events", { title: "one" })).rejects.toMatchObject({
      code: "ERR_NETWORK",
    })
    expect(calls).toBe(2)
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it.each(["blob", "text", "custom-transform"] as const)(
    "does not replay an unsupported %s body",
    async (kind) => {
      const fetchSpy = vi.fn()
      vi.stubGlobal("fetch", fetchSpy)
      const { default: client } = await import("@/api/client")
      let calls = 0
      client.defaults.adapter = async (config) => {
        calls += 1
        throw rejection(client, config)
      }
      const body = kind === "blob" ? new Blob(["body"]) : kind === "text" ? "body" : { ok: true }
      const config =
        kind === "custom-transform"
          ? { transformRequest: [(value: unknown) => value] }
          : { headers: { "Content-Type": "text/plain" } }
      await expect(client.post("/api/v1/events", body, config)).rejects.toMatchObject({
        response: { status: 403 },
      })
      expect(calls).toBe(1)
      expect(fetchSpy).not.toHaveBeenCalled()
    }
  )

  it("stops after a second marked 403", async () => {
    const fetchSpy = vi.fn(async () => new Response(null, { status: 204 }))
    vi.stubGlobal("fetch", fetchSpy)
    const { default: client } = await import("@/api/client")
    let attempts = 0
    client.defaults.adapter = async (config) => {
      attempts += 1
      throw rejection(client, config)
    }
    await expect(client.post("/api/v1/events", { title: "one" })).rejects.toMatchObject({
      response: { status: 403 },
    })
    expect(attempts).toBe(2)
    expect(fetchSpy).toHaveBeenCalledOnce()
  })

  it.each(["failure", "network"] as const)(
    "does not replay when refresh has a %s",
    async (mode) => {
      const fetchSpy =
        mode === "failure"
          ? vi.fn(async () => new Response(null, { status: 503 }))
          : vi.fn(async () => {
              throw new Error("offline")
            })
      vi.stubGlobal("fetch", fetchSpy)
      const { default: client } = await import("@/api/client")
      let attempts = 0
      client.defaults.adapter = async (config) => {
        attempts += 1
        throw rejection(client, config)
      }
      await expect(client.post("/api/v1/events", { title: "one" })).rejects.toMatchObject({
        response: { status: 403 },
      })
      expect(attempts).toBe(1)
      expect(fetchSpy).toHaveBeenCalledOnce()
    }
  )

  it.each(["missing", "malformed", "lookalike"] as const)(
    "does not replay or bootstrap twice when the refreshed cookie is %s",
    async (cookieState) => {
      const fetchSpy = vi.fn(async () => {
        document.cookie = "csrf_token=; Max-Age=0; path=/"
        if (cookieState === "malformed") document.cookie = "csrf_token=%; path=/"
        if (cookieState === "lookalike") document.cookie = "notcsrf_token=lookalike; path=/"
        return new Response(null, { status: 204 })
      })
      vi.stubGlobal("fetch", fetchSpy)
      const { default: client } = await import("@/api/client")
      let attempts = 0
      client.defaults.adapter = async (config) => {
        attempts += 1
        throw rejection(client, config)
      }
      try {
        await expect(client.post("/api/v1/events", { title: "one" })).rejects.toMatchObject({
          response: { status: 403 },
        })
        expect(attempts).toBe(1)
        expect(fetchSpy).toHaveBeenCalledOnce()
      } finally {
        document.cookie = "notcsrf_token=; Max-Age=0; path=/"
      }
    }
  )

  it("does not perform a second bootstrap if the cookie disappears just before replay", async () => {
    const fetchSpy = vi.fn(async () => {
      document.cookie = "csrf_token=new-session-proof; path=/"
      return new Response(null, { status: 204 })
    })
    vi.stubGlobal("fetch", fetchSpy)
    const { default: client } = await import("@/api/client")
    const request = client.request.bind(client)
    vi.spyOn(client, "request").mockImplementation((config) => {
      document.cookie = "csrf_token=; Max-Age=0; path=/"
      return request(config)
    })
    let attempts = 0
    client.defaults.adapter = async (config) => {
      attempts += 1
      throw rejection(client, config)
    }
    await expect(client.post("/api/v1/events", { title: "one" })).rejects.toMatchObject({
      response: { status: 403 },
    })
    expect(attempts).toBe(2)
    expect(fetchSpy).toHaveBeenCalledOnce()
  })

  it("cancels without replay when the session changes during refresh", async () => {
    let finishRefresh!: (response: Response) => void
    const fetchSpy = vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          finishRefresh = resolve
        })
    )
    vi.stubGlobal("fetch", fetchSpy)
    const { default: client } = await import("@/api/client")
    const { invalidateSessionEpoch } = await import("@/stores/sessionEpoch")
    let attempts = 0
    client.defaults.adapter = async (config) => {
      attempts += 1
      throw rejection(client, config)
    }
    const pending = client.post("/api/v1/events", { title: "one" }).catch((error: unknown) => error)
    await vi.waitFor(() => expect(fetchSpy).toHaveBeenCalledOnce())
    invalidateSessionEpoch()
    finishRefresh(new Response(null, { status: 204 }))
    expect(isCancel(await pending)).toBe(true)
    expect(attempts).toBe(1)
  })

  it("propagates cancellation to the refresh and does not replay", async () => {
    const controller = new AbortController()
    const fetchSpy = vi.fn(
      (_input: RequestInfo | URL, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener(
            "abort",
            () => reject(new DOMException("Aborted", "AbortError")),
            { once: true }
          )
        })
    )
    vi.stubGlobal("fetch", fetchSpy)
    const { default: client } = await import("@/api/client")
    let attempts = 0
    client.defaults.adapter = async (config) => {
      attempts += 1
      throw rejection(client, config)
    }
    const options = { headers: { "Idempotency-Key": "cancelled-recovery-key" } }
    const pending = client
      .post("/api/v1/events", { title: "one" }, { ...options, signal: controller.signal })
      .catch((error: unknown) => error)
    await vi.waitFor(() => expect(fetchSpy).toHaveBeenCalledOnce())
    controller.abort()
    expect(isCancel(await pending)).toBe(true)
    expect(attempts).toBe(1)
    client.defaults.adapter = async (config) => responseFor(config)
    await expect(client.post("/api/v1/events", { title: "one" }, options)).resolves.toMatchObject({
      status: 200,
    })
  })

  it("does not start refresh when the request aborts after the response is received", async () => {
    const fetchSpy = vi.fn()
    vi.stubGlobal("fetch", fetchSpy)
    const controller = new AbortController()
    const { default: client } = await import("@/api/client")
    let attempts = 0
    client.defaults.adapter = (config) =>
      new Promise((_resolve, reject) => {
        attempts += 1
        queueMicrotask(() => {
          reject(rejection(client, config))
          queueMicrotask(() => controller.abort())
        })
      })
    const result = await client
      .post("/api/v1/events", { title: "one" }, { signal: controller.signal })
      .catch((error: unknown) => error)
    expect(isCancel(result)).toBe(true)
    expect(attempts).toBe(1)
    expect(fetchSpy).not.toHaveBeenCalled()
  })
})

describe("forced CSRF bootstrap", () => {
  it("never fetches in SSR, Lighthouse, or after caller cancellation", async () => {
    const fetchSpy = vi.fn()
    vi.stubGlobal("fetch", fetchSpy)
    const { forceRefreshCsrfCookie } = await import("@/api/csrfRecovery")
    const controller = new AbortController()
    controller.abort()
    expect(await forceRefreshCsrfCookie(controller.signal)).toBe(false)
    vi.stubEnv("VITE_LHCI", "true")
    expect(await forceRefreshCsrfCookie()).toBe(false)
    vi.stubEnv("VITE_LHCI", "false")
    vi.stubGlobal("document", undefined)
    expect(await forceRefreshCsrfCookie()).toBe(false)
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it("aborts a bootstrap that exceeds its deadline", async () => {
    vi.useFakeTimers()
    const fetchSpy = vi.fn(
      (_input: RequestInfo | URL, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () =>
            reject(new DOMException("Aborted", "AbortError"))
          )
        })
    )
    vi.stubGlobal("fetch", fetchSpy)
    const { forceRefreshCsrfCookie } = await import("@/api/csrfRecovery")
    const pending = forceRefreshCsrfCookie()
    await vi.advanceTimersByTimeAsync(8_000)
    await expect(pending).resolves.toBe(false)
    expect(fetchSpy).toHaveBeenCalledOnce()
  })
})
