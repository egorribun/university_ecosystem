import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { AxiosHeaders, isCancel } from "axios"

const SESSION_GENERATION_KEY = "ecosystem.session.generation.v1"

describe("api/client — production CSRF bootstrap", () => {
  beforeEach(() => {
    vi.resetModules()
    localStorage.removeItem(SESSION_GENERATION_KEY)
    vi.stubEnv("MODE", "production")
    document.cookie = "csrf_token=; Max-Age=0; path=/"
  })

  afterEach(() => {
    localStorage.removeItem(SESSION_GENERATION_KEY)
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
    document.cookie = "csrf_token=; Max-Age=0; path=/"
  })

  it("cancels an unsafe request if another tab changes generation during CSRF bootstrap", async () => {
    localStorage.setItem(
      SESSION_GENERATION_KEY,
      JSON.stringify({ nonce: "tab-a-generation", hash: "profile-a" })
    )
    let resolveBootstrap!: (response: Response) => void
    const bootstrap = new Promise<Response>((resolve) => {
      resolveBootstrap = resolve
    })
    const fetchSpy = vi.fn(() => bootstrap)
    vi.stubGlobal("fetch", fetchSpy)

    const { default: client } = await import("@/api/client")
    const adapter = vi.fn(async (config): Promise<import("axios").AxiosResponse> => ({
      config,
      data: { ok: true },
      status: 200,
      statusText: "OK",
      headers: new AxiosHeaders(),
      request: {},
    }))
    client.defaults.adapter = adapter

    const pending = client.post("/events", { title: "event" })
    const settled = pending.catch((error: unknown) => error)
    await vi.waitFor(() => expect(fetchSpy).toHaveBeenCalledOnce())

    // A separate tab changes the shared session while this tab awaits CSRF.
    localStorage.setItem(
      SESSION_GENERATION_KEY,
      JSON.stringify({ nonce: "tab-b-generation", hash: "profile-b" })
    )
    resolveBootstrap({ ok: true } as Response)

    const result = await settled
    expect(isCancel(result)).toBe(true)
    expect(adapter).not.toHaveBeenCalled()
  })

  it("cancels when the local epoch changes during CSRF bootstrap", async () => {
    const generation = JSON.stringify({ nonce: "local-epoch-generation", hash: "profile-a" })
    localStorage.setItem(SESSION_GENERATION_KEY, generation)
    let resolveBootstrap!: (response: Response) => void
    const bootstrap = new Promise<Response>((resolve) => {
      resolveBootstrap = resolve
    })
    const fetchSpy = vi.fn(() => bootstrap)
    vi.stubGlobal("fetch", fetchSpy)

    const { default: client } = await import("@/api/client")
    const { invalidateSessionEpoch } = await import("@/stores/sessionEpoch")
    const adapter = vi.fn(async (config): Promise<import("axios").AxiosResponse> => ({
      config,
      data: { ok: true },
      status: 200,
      statusText: "OK",
      headers: new AxiosHeaders(),
      request: {},
    }))
    client.defaults.adapter = adapter

    const pending = client.post("/events", { title: "event" })
    const settled = pending.catch((error: unknown) => error)
    await vi.waitFor(() => expect(fetchSpy).toHaveBeenCalledOnce())

    // Local invalidation changes only the in-memory epoch, not the shared generation.
    invalidateSessionEpoch()
    expect(localStorage.getItem(SESSION_GENERATION_KEY)).toBe(generation)
    resolveBootstrap({ ok: true } as Response)

    const result = await settled
    expect(isCancel(result)).toBe(true)
    expect(adapter).not.toHaveBeenCalled()
  })

  it.each(["same-nonce-hash", "absent", "unavailable"] as const)(
    "cancels a pending private API request when a failed full-generation receipt changes to %s",
    async (storageState) => {
      const original = JSON.stringify({ nonce: "prior-generation", hash: null })
      localStorage.setItem(SESSION_GENERATION_KEY, original)
      const { default: client } = await import("@/api/client")
      const { rotateBrowserSession } = await import("@/stores/sessionEpoch")
      const storageWrite = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
        throw new DOMException("blocked", "SecurityError")
      })
      let restoreStorageRead: (() => void) | undefined
      let resolveBootstrap!: (response: Response) => void
      let bootstrapFinished = false
      const bootstrap = new Promise<Response>((resolve) => {
        resolveBootstrap = resolve
      })
      const finishBootstrap = () => {
        if (!bootstrapFinished) {
          bootstrapFinished = true
          resolveBootstrap({ ok: true } as Response)
        }
      }
      const fetchSpy = vi.fn(() => bootstrap)
      vi.stubGlobal("fetch", fetchSpy)
      const adapter = vi.fn(async (config): Promise<import("axios").AxiosResponse> => ({
        config,
        data: { ok: true },
        status: 200,
        statusText: "OK",
        headers: new AxiosHeaders(),
        request: {},
      }))
      client.defaults.adapter = adapter
      let settledRequest: Promise<unknown> | undefined

      try {
        rotateBrowserSession()
        storageWrite.mockRestore()

        const request = client.post("/events", { title: "event" })
        const settled = request.catch((error: unknown) => error)
        settledRequest = settled
        await vi.waitFor(() => expect(fetchSpy).toHaveBeenCalledOnce())

        if (storageState === "same-nonce-hash") {
          localStorage.setItem(
            SESSION_GENERATION_KEY,
            JSON.stringify({ nonce: "prior-generation", hash: "different-profile" })
          )
        } else if (storageState === "absent") {
          localStorage.removeItem(SESSION_GENERATION_KEY)
        } else {
          const storageRead = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
            throw new DOMException("blocked", "SecurityError")
          })
          restoreStorageRead = () => storageRead.mockRestore()
        }

        finishBootstrap()
        const result = await settled
        expect(isCancel(result)).toBe(true)
        expect(adapter).not.toHaveBeenCalled()
      } finally {
        finishBootstrap()
        await settledRequest
        storageWrite.mockRestore()
        restoreStorageRead?.()
      }
    }
  )

  it("keeps auth bootstrap requests available after a remote generation update", async () => {
    localStorage.setItem(
      SESSION_GENERATION_KEY,
      JSON.stringify({ nonce: "tab-a-generation", hash: "profile-a" })
    )
    const { default: client } = await import("@/api/client")
    const { isCurrentBrowserSession } = await import("@/stores/sessionEpoch")
    localStorage.setItem(
      SESSION_GENERATION_KEY,
      JSON.stringify({ nonce: "tab-b-generation", hash: "profile-b" })
    )

    expect(isCurrentBrowserSession()).toBe(false)
    const requests: string[] = []
    client.defaults.adapter = async (config): Promise<import("axios").AxiosResponse> => {
      requests.push(config.url ?? "")
      return {
        config,
        data: config.url === "/users/me" ? { id: "profile-b" } : { signing_key: "key-b" },
        status: 200,
        statusText: "OK",
        headers: new AxiosHeaders(),
        request: {},
      }
    }

    const profile = await client.get("/users/me", { skipRateLimitQueue: true } as never)
    const signingKey = await client.get("/auth/session/signing-key", {
      skipRateLimitQueue: true,
    } as never)

    expect(profile.data).toEqual({ id: "profile-b" })
    expect(signingKey.data).toEqual({ signing_key: "key-b" })
    expect(requests).toEqual(["/users/me", "/auth/session/signing-key"])
  })

  it("blocks unrelated requests that start stale before CSRF or adapter work", async () => {
    localStorage.setItem(
      SESSION_GENERATION_KEY,
      JSON.stringify({ nonce: "tab-a-generation", hash: "profile-a" })
    )
    const fetchSpy = vi.fn()
    vi.stubGlobal("fetch", fetchSpy)
    const { default: client } = await import("@/api/client")
    localStorage.setItem(
      SESSION_GENERATION_KEY,
      JSON.stringify({ nonce: "tab-b-generation", hash: "profile-b" })
    )
    const adapter = vi.fn(async (config): Promise<import("axios").AxiosResponse> => ({
      config,
      data: { ok: true },
      status: 200,
      statusText: "OK",
      headers: new AxiosHeaders(),
      request: {},
    }))
    client.defaults.adapter = adapter

    const unrelatedGet = client.get("/news").catch((error: unknown) => error)
    const unsafePost = client.post("/events", { title: "event" }).catch((error: unknown) => error)

    expect(isCancel(await unrelatedGet)).toBe(true)
    expect(isCancel(await unsafePost)).toBe(true)
    expect(adapter).not.toHaveBeenCalled()
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it("restricts stale-session bootstrap to exact same-origin GET endpoints", async () => {
    localStorage.setItem(
      SESSION_GENERATION_KEY,
      JSON.stringify({ nonce: "tab-a-generation", hash: "profile-a" })
    )
    const { default: client } = await import("@/api/client")
    localStorage.setItem(
      SESSION_GENERATION_KEY,
      JSON.stringify({ nonce: "tab-b-generation", hash: "profile-b" })
    )
    const adapter = vi.fn(async (config): Promise<import("axios").AxiosResponse> => ({
      config,
      data: { ok: true },
      status: 200,
      statusText: "OK",
      headers: new AxiosHeaders(),
      request: {},
    }))
    client.defaults.adapter = adapter

    const denied = await Promise.all([
      client.post("/users/me", {}).catch((error: unknown) => error),
      client.get("/users/me?include=private").catch((error: unknown) => error),
      client.get("/users/me/extra").catch((error: unknown) => error),
      client.get("https://example.invalid/api/v1/users/me").catch((error: unknown) => error),
    ])

    expect(denied.every(isCancel)).toBe(true)
    expect(adapter).not.toHaveBeenCalled()
  })

  it("cancels stale requests whose URL cannot resolve to an allowed same-origin route", async () => {
    localStorage.setItem(
      SESSION_GENERATION_KEY,
      JSON.stringify({ nonce: "tab-a-generation", hash: "profile-a" })
    )
    const { default: client } = await import("@/api/client")
    localStorage.setItem(
      SESSION_GENERATION_KEY,
      JSON.stringify({ nonce: "tab-b-generation", hash: "profile-b" })
    )
    const adapter = vi.fn(async (config): Promise<import("axios").AxiosResponse> => ({
      config,
      data: { ok: true },
      status: 200,
      statusText: "OK",
      headers: new AxiosHeaders(),
      request: {},
    }))
    client.defaults.adapter = adapter

    const malformed = await client.get("https://[").catch((error: unknown) => error)
    const missing = await client
      .request({ method: "get", url: undefined })
      .catch((error: unknown) => error)

    expect(isCancel(malformed)).toBe(true)
    expect(isCancel(missing)).toBe(true)
    expect(adapter).not.toHaveBeenCalled()
  })

  it("rejects a protocol-relative versioned profile URL as stale-session bootstrap", async () => {
    localStorage.setItem(
      SESSION_GENERATION_KEY,
      JSON.stringify({ nonce: "tab-a-generation", hash: "profile-a" })
    )
    const { default: client } = await import("@/api/client")
    client.defaults.baseURL = "/api/v1"
    localStorage.setItem(
      SESSION_GENERATION_KEY,
      JSON.stringify({ nonce: "tab-b-generation", hash: "profile-b" })
    )
    const adapter = vi.fn(async (config): Promise<import("axios").AxiosResponse> => ({
      config,
      data: { id: "profile-b" },
      status: 200,
      statusText: "OK",
      headers: new AxiosHeaders(),
      request: {},
    }))
    client.defaults.adapter = adapter

    const result = await client.get("//localhost/api/v1/users/me").catch((error: unknown) => error)

    expect(isCancel(result)).toBe(true)
    expect(adapter).not.toHaveBeenCalled()
  })

  it("rejects same-origin absolute and protocol-relative bootstrap URLs with a versioned base", async () => {
    localStorage.setItem(
      SESSION_GENERATION_KEY,
      JSON.stringify({ nonce: "tab-a-generation", hash: "profile-a" })
    )
    const { default: client } = await import("@/api/client")
    client.defaults.baseURL = "/api/v1"
    localStorage.setItem(
      SESSION_GENERATION_KEY,
      JSON.stringify({ nonce: "tab-b-generation", hash: "profile-b" })
    )
    const adapter = vi.fn(async (config): Promise<import("axios").AxiosResponse> => ({
      config,
      data: { id: "profile-b" },
      status: 200,
      statusText: "OK",
      headers: new AxiosHeaders(),
      request: {},
    }))
    client.defaults.adapter = adapter

    const absoluteUrl = window.location.origin + "/api/v1/users/me"
    const protocolRelativeUrl = "//" + window.location.host + "/api/v1/users/me"
    const denied = await Promise.all(
      [absoluteUrl, protocolRelativeUrl].map((url) =>
        client.get(url).catch((error: unknown) => error)
      )
    )

    expect(denied.every(isCancel)).toBe(true)
    expect(adapter).not.toHaveBeenCalled()
  })

  it("allows same-origin absolute bootstrap with an unversioned base only", async () => {
    localStorage.setItem(
      SESSION_GENERATION_KEY,
      JSON.stringify({ nonce: "tab-a-generation", hash: "profile-a" })
    )
    const { default: client } = await import("@/api/client")
    client.defaults.baseURL = "/gateway"
    localStorage.setItem(
      SESSION_GENERATION_KEY,
      JSON.stringify({ nonce: "tab-b-generation", hash: "profile-b" })
    )
    const requests: string[] = []
    const adapter = vi.fn(async (config): Promise<import("axios").AxiosResponse> => {
      requests.push(config.url ?? "")
      return {
        config,
        data: { id: "profile-b" },
        status: 200,
        statusText: "OK",
        headers: new AxiosHeaders(),
        request: {},
      }
    })
    client.defaults.adapter = adapter

    const profileUrl = window.location.origin + "/users/me"
    const profile = await client.get(profileUrl)
    const unrelated = await client
      .get(window.location.origin + "/news")
      .catch((error: unknown) => error)

    expect(profile.data).toEqual({ id: "profile-b" })
    expect(isCancel(unrelated)).toBe(true)
    expect(requests).toEqual([profileUrl])
    expect(adapter).toHaveBeenCalledOnce()
  })

  it("cancels a triple-slash URL that Axios treats as an absolute network path", async () => {
    localStorage.setItem(
      SESSION_GENERATION_KEY,
      JSON.stringify({ nonce: "tab-a-generation", hash: "profile-a" })
    )
    const { default: client } = await import("@/api/client")
    localStorage.setItem(
      SESSION_GENERATION_KEY,
      JSON.stringify({ nonce: "tab-b-generation", hash: "profile-b" })
    )
    const adapter = vi.fn(async (config): Promise<import("axios").AxiosResponse> => ({
      config,
      data: { id: "profile-b" },
      status: 200,
      statusText: "OK",
      headers: new AxiosHeaders(),
      request: {},
    }))
    client.defaults.adapter = adapter

    const result = await client.get("///users/me").catch((error: unknown) => error)

    expect(isCancel(result)).toBe(true)
    expect(adapter).not.toHaveBeenCalled()
  })
  it("keeps stale-path checks fail-closed when request and default base URLs are absent", async () => {
    localStorage.setItem(
      SESSION_GENERATION_KEY,
      JSON.stringify({ nonce: "tab-a-generation", hash: "profile-a" })
    )
    const { default: client } = await import("@/api/client")
    localStorage.setItem(
      SESSION_GENERATION_KEY,
      JSON.stringify({ nonce: "tab-b-generation", hash: "profile-b" })
    )
    const adapter = vi.fn(async (config): Promise<import("axios").AxiosResponse> => ({
      config,
      data: { ok: true },
      status: 200,
      statusText: "OK",
      headers: new AxiosHeaders(),
      request: {},
    }))
    client.defaults.adapter = adapter
    const originalBaseURL = client.defaults.baseURL
    let nullOverride: unknown
    let noConfiguredBase: unknown

    try {
      client.defaults.baseURL = "/api/v1"
      nullOverride = await client
        .get("/news", { baseURL: null as unknown as string })
        .catch((error: unknown) => error)

      client.defaults.baseURL = undefined
      noConfiguredBase = await client.get("/news").catch((error: unknown) => error)
    } finally {
      client.defaults.baseURL = originalBaseURL
    }

    expect(isCancel(nullOverride)).toBe(true)
    expect(isCancel(noConfiguredBase)).toBe(true)
    expect(adapter).not.toHaveBeenCalled()
  })
  it("keeps initial unbound profile and signing-key hydration available", async () => {
    const { default: client } = await import("@/api/client")
    localStorage.setItem(
      SESSION_GENERATION_KEY,
      JSON.stringify({ nonce: "hydrated-generation", hash: "profile-b" })
    )
    const { isCurrentBrowserSession } = await import("@/stores/sessionEpoch")
    expect(isCurrentBrowserSession()).toBe(false)

    const requests: string[] = []
    client.defaults.adapter = async (config): Promise<import("axios").AxiosResponse> => {
      requests.push(config.url ?? "")
      return {
        config,
        data: config.url === "/users/me" ? { id: "profile-b" } : { signing_key: "key-b" },
        status: 200,
        statusText: "OK",
        headers: new AxiosHeaders(),
        request: {},
      }
    }

    await client.get("/users/me", { skipRateLimitQueue: true } as never)
    await client.get("/auth/session/signing-key", { skipRateLimitQueue: true } as never)

    expect(requests).toEqual(["/users/me", "/auth/session/signing-key"])
  })

  it("keeps current-session login, registration, logout, and MFA requests available", async () => {
    localStorage.setItem(
      SESSION_GENERATION_KEY,
      JSON.stringify({ nonce: "active-generation", hash: "profile-a" })
    )
    document.cookie = "csrf_token=existing-token; path=/"
    const { default: client } = await import("@/api/client")
    const { rotateBrowserSession } = await import("@/stores/sessionEpoch")
    const requests: string[] = []
    client.defaults.adapter = async (config): Promise<import("axios").AxiosResponse> => {
      requests.push(`${config.method}:${config.url}`)
      return {
        config,
        data: { ok: true },
        status: 200,
        statusText: "OK",
        headers: new AxiosHeaders(),
        request: {},
      }
    }

    rotateBrowserSession()
    await client.post("/auth/login", {}, { skipRateLimitQueue: true } as never)
    await client.post("/auth/register", {})
    rotateBrowserSession()
    await client.post("/auth/logout")
    rotateBrowserSession()
    await client.post("/auth/mfa/verify", {}, { skipRateLimitQueue: true } as never)
    await client.post("/auth/mfa/step-up", {}, { skipRateLimitQueue: true } as never)

    expect(requests).toEqual([
      "post:/auth/login",
      "post:/auth/register",
      "post:/auth/logout",
      "post:/auth/mfa/verify",
      "post:/auth/mfa/step-up",
    ])
  })

  it("keeps live login available when browser generation storage is blocked", async () => {
    document.cookie = "csrf_token=existing-token; path=/"
    const { default: client } = await import("@/api/client")
    const { rotateBrowserSession } = await import("@/stores/sessionEpoch")
    const storageWrite = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError")
    })
    const adapter = vi.fn(async (config): Promise<import("axios").AxiosResponse> => ({
      config,
      data: { ok: true },
      status: 200,
      statusText: "OK",
      headers: new AxiosHeaders(),
      request: {},
    }))
    client.defaults.adapter = adapter

    try {
      rotateBrowserSession()
      await client.post("/auth/login", {}, { skipRateLimitQueue: true } as never)
      expect(adapter).toHaveBeenCalledOnce()
    } finally {
      storageWrite.mockRestore()
    }
  })

  it("keeps login available after a failed rotation of a readable prior generation", async () => {
    localStorage.setItem(
      SESSION_GENERATION_KEY,
      JSON.stringify({ nonce: "prior-generation", hash: "prior-profile" })
    )
    document.cookie = "csrf_token=existing-token; path=/"
    const { default: client } = await import("@/api/client")
    const { getBrowserSessionGeneration, hasStaleBrowserSessionBinding, rotateBrowserSession } =
      await import("@/stores/sessionEpoch")
    const storageWrite = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError")
    })
    const adapter = vi.fn(async (config): Promise<import("axios").AxiosResponse> => ({
      config,
      data: { ok: true },
      status: 200,
      statusText: "OK",
      headers: new AxiosHeaders(),
      request: {},
    }))
    client.defaults.adapter = adapter

    try {
      rotateBrowserSession()
      expect(getBrowserSessionGeneration()).toBe("prior-generation")
      expect(hasStaleBrowserSessionBinding()).toBe(false)
      await client.post("/auth/login", {}, { skipRateLimitQueue: true } as never)
      expect(adapter).toHaveBeenCalledOnce()

      storageWrite.mockRestore()
      localStorage.setItem(
        SESSION_GENERATION_KEY,
        JSON.stringify({ nonce: "remote-generation", hash: "remote-profile" })
      )
      expect(hasStaleBrowserSessionBinding()).toBe(true)
      const unrelated = await client.get("/news").catch((error: unknown) => error)
      expect(isCancel(unrelated)).toBe(true)
      expect(adapter).toHaveBeenCalledOnce()
    } finally {
      storageWrite.mockRestore()
    }
  })

  it("keeps login recovery available but blocks logout when storage becomes unreadable after a failed rotation", async () => {
    localStorage.setItem(
      SESSION_GENERATION_KEY,
      JSON.stringify({ nonce: "active-generation", hash: "active-profile" })
    )
    document.cookie = "csrf_token=existing-token; path=/"
    const { default: client } = await import("@/api/client")
    const { rotateBrowserSession, hasStaleBrowserSessionBinding } =
      await import("@/stores/sessionEpoch")
    const storageWrite = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError")
    })
    const requests: string[] = []
    client.defaults.adapter = async (config): Promise<import("axios").AxiosResponse> => {
      requests.push(`${config.method}:${config.url}`)
      return {
        config,
        data: { ok: true },
        status: 200,
        statusText: "OK",
        headers: new AxiosHeaders(),
        request: {},
      }
    }

    let restoreStorageRead: (() => void) | undefined
    try {
      rotateBrowserSession()
      expect(localStorage.getItem(SESSION_GENERATION_KEY)).toContain("active-generation")
      expect(hasStaleBrowserSessionBinding()).toBe(false)
      const storageRead = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
        throw new DOMException("blocked", "SecurityError")
      })
      restoreStorageRead = () => storageRead.mockRestore()
      expect(hasStaleBrowserSessionBinding()).toBe(true)
      await client.post("/auth/login", {}, { skipRateLimitQueue: true } as never)
      rotateBrowserSession()
      const logout = await client.post("/auth/logout", {}).catch((error: unknown) => error)
      expect(isCancel(logout)).toBe(true)
      expect(requests).toEqual(["post:/auth/login"])
    } finally {
      storageWrite.mockRestore()
      restoreStorageRead?.()
    }
  })

  it("allows only auth recovery while a stale tab cannot rotate the shared generation", async () => {
    localStorage.setItem(
      SESSION_GENERATION_KEY,
      JSON.stringify({ nonce: "tab-a-generation", hash: "profile-a" })
    )
    const { default: client } = await import("@/api/client")
    const { rotateBrowserSession, hasStaleBrowserSessionBinding } =
      await import("@/stores/sessionEpoch")
    localStorage.setItem(
      SESSION_GENERATION_KEY,
      JSON.stringify({ nonce: "tab-b-generation", hash: "profile-b" })
    )
    const fetchSpy = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal("fetch", fetchSpy)
    const storageWrite = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError")
    })
    const requests: string[] = []
    client.defaults.adapter = async (config): Promise<import("axios").AxiosResponse> => {
      requests.push(`${config.method}:${config.url}`)
      return {
        config,
        data: { ok: true },
        status: 200,
        statusText: "OK",
        headers: new AxiosHeaders(),
        request: {},
      }
    }

    let restoreStorageRead: (() => void) | undefined
    try {
      rotateBrowserSession()
      expect(localStorage.getItem(SESSION_GENERATION_KEY)).toContain("tab-b-generation")
      expect(hasStaleBrowserSessionBinding()).toBe(true)
      const storageRead = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
        throw new DOMException("blocked", "SecurityError")
      })
      restoreStorageRead = () => storageRead.mockRestore()
      expect(hasStaleBrowserSessionBinding()).toBe(true)
      await client.post("/auth/login", {}, {
        baseURL: "/api/v1",
        skipRateLimitQueue: true,
      } as never)
      await client.post("/auth/mfa/verify", {}, { skipRateLimitQueue: true } as never)
      const csrfCallsAfterRecovery = fetchSpy.mock.calls.length
      const foreignBaseLogin = await client
        .post("/auth/login", {}, {
          baseURL: "https://foreign.invalid/api/v1",
          skipRateLimitQueue: true,
        } as never)
        .catch((error: unknown) => error)
      const queryAlias = await client
        .post("/auth/login?continue=/news", {}, { skipRateLimitQueue: true } as never)
        .catch((error: unknown) => error)
      const fragmentAlias = await client
        .post("/auth/login#child", {}, { skipRateLimitQueue: true } as never)
        .catch((error: unknown) => error)
      const childPathAlias = await client
        .post("/auth/login/child", {}, { skipRateLimitQueue: true } as never)
        .catch((error: unknown) => error)
      const credentialedBase = await client
        .post("/auth/login", {}, {
          baseURL: window.location.origin.replace("://", "://user:pass@") + "/api/v1",
          skipRateLimitQueue: true,
        } as never)
        .catch((error: unknown) => error)
      const absoluteVersionedAlias = await client
        .post(window.location.origin + "/api/v1/auth/login", {}, {
          baseURL: "/api/v1",
          skipRateLimitQueue: true,
        } as never)
        .catch((error: unknown) => error)
      const absoluteLogin = await client
        .post(window.location.origin + "/auth/login", {}, {
          baseURL: "",
          skipRateLimitQueue: true,
        } as never)
        .catch((error: unknown) => error)
      const absoluteMfa = await client
        .post(window.location.origin + "/auth/mfa/verify", {}, {
          baseURL: "",
          skipRateLimitQueue: true,
        } as never)
        .catch((error: unknown) => error)

      const unrelatedGet = await client.get("/news").catch((error: unknown) => error)
      const unrelatedMutation = await client.post("/events", {}).catch((error: unknown) => error)
      const logout = await client.post("/auth/logout", {}).catch((error: unknown) => error)

      expect(isCancel(foreignBaseLogin)).toBe(true)
      expect(
        [
          queryAlias,
          fragmentAlias,
          childPathAlias,
          credentialedBase,
          absoluteVersionedAlias,
          absoluteLogin,
          absoluteMfa,
        ].every(isCancel)
      ).toBe(true)
      expect(isCancel(unrelatedGet)).toBe(true)
      expect(isCancel(unrelatedMutation)).toBe(true)
      expect(isCancel(logout)).toBe(true)
      expect(fetchSpy).toHaveBeenCalledTimes(csrfCallsAfterRecovery)
      expect(requests).toEqual(["post:/auth/login", "post:/auth/mfa/verify"])
    } finally {
      storageWrite.mockRestore()
      restoreStorageRead?.()
    }
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
    expect(second).toBe(first)
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

  it("does not access browser state when invoked during SSR", async () => {
    const fetchSpy = vi.fn()
    vi.stubGlobal("fetch", fetchSpy)
    vi.stubGlobal("document", undefined)
    const { ensureCsrfCookie } = await import("@/api/client")

    await expect(ensureCsrfCookie()).resolves.toBeUndefined()
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it("bootstraps CSRF for unsafe requests but skips the bootstrap endpoint itself", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal("fetch", fetchSpy)
    const { default: client } = await import("@/api/client")
    const requestHandler = (client.interceptors.request as any).handlers.find(
      (handler: { fulfilled?: unknown }) => typeof handler.fulfilled === "function"
    )?.fulfilled as (
      config: import("axios").InternalAxiosRequestConfig
    ) => Promise<import("axios").InternalAxiosRequestConfig>

    await requestHandler({
      method: "post",
      url: "/events",
      headers: {},
      data: { title: "event" },
    } as import("axios").InternalAxiosRequestConfig)
    expect(fetchSpy).toHaveBeenCalledOnce()

    await requestHandler({
      method: "post",
      url: "/auth/csrf-cookie",
      headers: {},
      data: {},
    } as import("axios").InternalAxiosRequestConfig)
    expect(fetchSpy).toHaveBeenCalledOnce()
  })
})
