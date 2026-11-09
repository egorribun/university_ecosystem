import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { AxiosHeaders, type AxiosResponse } from "axios"

import {
  applyEtagHeader,
  clearCachesOnLogout,
  etagCache,
  handleEtagResponse,
  incrementSessionEpoch,
  registerSigningKeyAccessor,
  responseCache,
} from "../etagCache"

const deferred = () => {
  let resolve!: () => void
  const promise = new Promise<void>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

const KEY = "events:race"
const response = (version: number, status = 200): AxiosResponse => ({
  status,
  statusText: "OK",
  headers: AxiosHeaders.from({ etag: `"v${version}"`, "content-type": "application/json" }),
  data: status === 304 ? null : { version },
  config: { headers: new AxiosHeaders() },
})

const pauseNextSign = () => {
  const entered = deferred()
  const gate = deferred()
  const realSign = crypto.subtle.sign.bind(crypto.subtle)
  vi.spyOn(crypto.subtle, "sign").mockImplementationOnce(async (...args) => {
    entered.resolve()
    await gate.promise
    return realSign(...args)
  })
  return { entered: entered.promise, release: gate.resolve }
}

beforeEach(() => {
  clearCachesOnLogout()
  registerSigningKeyAccessor(() => "race-session-a")
})

afterEach(() => {
  vi.restoreAllMocks()
  clearCachesOnLogout()
  registerSigningKeyAccessor(() => null)
})

describe("ETag cache concurrent publication", () => {
  it("does not let an older HMAC overwrite a newer response body", async () => {
    const pause = pauseNextSign()
    const older = handleEtagResponse(response(1), KEY)
    await pause.entered
    try {
      await handleEtagResponse(response(2), KEY)
    } finally {
      pause.release()
      await older
    }

    expect(etagCache.get(KEY)).toBe('"v2"')
    expect(responseCache.get(KEY)?.data).toEqual({ version: 2 })
    const notModified = response(2, 304)
    await handleEtagResponse(notModified, KEY)
    expect(notModified).toMatchObject({ status: 200, data: { version: 2 } })
  })

  it("does not pair a pending ETag with the previously cached body", async () => {
    await handleEtagResponse(response(1), KEY)
    const pause = pauseNextSign()
    const newer = handleEtagResponse(response(2), KEY)
    await pause.entered
    try {
      const config = { headers: new AxiosHeaders() }
      applyEtagHeader(config, KEY)
      expect(config.headers.has("if-none-match")).toBe(false)
      expect(responseCache.get(KEY)).toBeUndefined()
    } finally {
      pause.release()
      await newer
    }
    expect(responseCache.get(KEY)?.data).toEqual({ version: 2 })
  })

  it("does not overwrite a newer cache with an older 304 validator", async () => {
    await handleEtagResponse(response(2), KEY)
    const notModified = response(1, 304)
    await handleEtagResponse(notModified, KEY)
    expect(notModified).toMatchObject({ status: 304, data: null })
    expect(etagCache.get(KEY)).toBe('"v2"')
    expect(responseCache.get(KEY)?.data).toEqual({ version: 2 })
  })

  it("keeps a stale 304 bodiless when its validator was evicted, without touching newer state", async () => {
    await handleEtagResponse(response(1), KEY)
    const notModified = response(1, 304)
    etagCache.delete(KEY)
    responseCache.set(KEY, { data: { version: 3 }, hmac: "unused", ts: Date.now() })
    await handleEtagResponse(notModified, KEY)
    expect(notModified).toMatchObject({ status: 304, data: null })
    expect(etagCache.get(KEY)).toBeUndefined()
    expect(responseCache.get(KEY)?.data).toEqual({ version: 3 })
  })

  it("discards a 304 whose entry was replaced while its HMAC was verified", async () => {
    await handleEtagResponse(response(1), KEY)
    const pause = pauseNextSign()
    const notModified = response(1, 304)
    const pending = handleEtagResponse(notModified, KEY)
    await pause.entered
    try {
      await handleEtagResponse(response(2), KEY)
    } finally {
      pause.release()
      await pending
    }
    expect(notModified).toMatchObject({ status: 304, data: null })
    expect(responseCache.get(KEY)?.data).toEqual({ version: 2 })
  })

  it("does not resurrect a pending write after an explicit cache reset", async () => {
    const pause = pauseNextSign()
    const pending = handleEtagResponse(response(1), KEY)
    await pause.entered
    etagCache.clear()
    responseCache.clear()
    pause.release()
    await pending
    expect(etagCache.get(KEY)).toBeUndefined()
    expect(responseCache.get(KEY)).toBeUndefined()
  })

  it("invalidates the old body even when the replacement is not cacheable JSON", async () => {
    await handleEtagResponse(response(1), KEY)
    const html = response(2)
    html.headers = AxiosHeaders.from({ etag: '"v2"', "content-type": "text/html" })
    html.data = "<html>unavailable</html>"
    await handleEtagResponse(html, KEY)
    expect(etagCache.get(KEY)).toBe('"v2"')
    expect(responseCache.get(KEY)).toBeUndefined()
  })

  it("keeps different keys independent while HMAC completion is reordered", async () => {
    const pause = pauseNextSign()
    const pending = handleEtagResponse(response(1), KEY)
    await pause.entered
    try {
      await handleEtagResponse(response(2), "other:key")
    } finally {
      pause.release()
      await pending
    }
    expect(responseCache.get(KEY)?.data).toEqual({ version: 1 })
    expect(responseCache.get("other:key")?.data).toEqual({ version: 2 })
  })
})

describe("ETag cache session ownership", () => {
  it.each(["logout", "login", "key rotation"])(
    "does not deliver an old 304 after %s during HMAC verification",
    async (transition) => {
      await handleEtagResponse(response(1), KEY)
      const pause = pauseNextSign()
      const notModified = response(1, 304)
      const pending = handleEtagResponse(notModified, KEY)
      await pause.entered
      if (transition === "logout") clearCachesOnLogout()
      if (transition === "login") incrementSessionEpoch()
      if (transition === "key rotation") registerSigningKeyAccessor(() => "race-session-b")
      pause.release()
      await pending
      expect(notModified).toMatchObject({ status: 304, data: null })
    }
  )

  it("does not publish a 200 if the signing key changed without an epoch increment", async () => {
    const pause = pauseNextSign()
    const pending = handleEtagResponse(response(1), KEY)
    await pause.entered
    registerSigningKeyAccessor(() => "race-session-b")
    pause.release()
    await pending
    expect(responseCache.get(KEY)).toBeUndefined()
  })
})
