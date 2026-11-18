import { EventEmitter } from "node:events"
import { Buffer } from "node:buffer"
import { spawnSync } from "node:child_process"
import https from "node:https"
import { resolve } from "node:path"
import process from "node:process"
import { afterEach, describe, expect, it, vi } from "vitest"
import { fetchAlpineZlibArchive } from "../scripts/fetch-alpine-zlib-archive.mjs"

const archives = {
  x86_64: {
    url: "https://dl-cdn.alpinelinux.org/alpine/v3.24/releases/x86_64/alpine-virt-3.24.3-x86_64.iso",
    range: "bytes=15585280-15641489",
    contentRange: "bytes 15585280-15641489/70254592",
    size: 56210,
  },
  aarch64: {
    url: "https://dl-cdn.alpinelinux.org/alpine/v3.24/releases/aarch64/alpine-virt-3.24.3-aarch64.iso",
    range: "bytes=16148480-16202813",
    contentRange: "bytes 16148480-16202813/93452288",
    size: 54334,
  },
}

function exchange(arch, { status = 206, headers = {}, outcome = "complete" } = {}) {
  const spec = archives[arch]
  const request = new EventEmitter()
  request.destroy = vi.fn()
  const response = new EventEmitter()
  response.statusCode = status
  response.headers = {
    "content-range": spec.contentRange,
    "content-length": String(spec.size),
    ...headers,
  }
  response.complete = false
  response.destroy = vi.fn()
  const get = vi.spyOn(https, "get").mockImplementation((url, options, callback) => {
    Promise.resolve().then(() => {
      if (outcome === "request-error") {
        request.emit("error", new Error("synthetic request failure"))
        return
      }
      if (outcome === "no-response") return
      callback(response)
      if (response.destroy.mock.calls.length || outcome === "stall") return
      const first = Math.floor(spec.size / 2)
      response.emit("data", Buffer.alloc(first, 97))
      if (outcome === "read-error") {
        response.emit("error", new Error("synthetic read failure"))
        return
      }
      if (outcome === "closed") {
        response.emit("close")
        return
      }
      if (outcome === "aborted") {
        response.emit("aborted")
        return
      }
      if (outcome === "non-buffer") {
        response.emit("data", "not a buffer")
        return
      }
      const rest = spec.size - first + (outcome === "overrun" ? 1 : outcome === "short" ? -1 : 0)
      response.emit("data", Buffer.alloc(rest, 98))
      if (outcome === "overrun") {
        response.emit("data", Buffer.from("ignored"))
        response.emit("error", new Error("late synthetic read failure"))
      }
      response.complete = outcome !== "end-incomplete"
      response.emit("end")
      if (response.complete) response.emit("close")
    })
    return request
  })
  return { get, request, response }
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe.each(Object.keys(archives))("fixed %s archive", (arch) => {
  it("fetches only the exact approved HTTPS byte range", async () => {
    const { get } = exchange(arch)
    const body = await fetchAlpineZlibArchive(arch)
    const first = Math.floor(archives[arch].size / 2)
    expect(body).toEqual(
      Buffer.concat([Buffer.alloc(first, 97), Buffer.alloc(archives[arch].size - first, 98)])
    )
    expect(get).toHaveBeenCalledOnce()
    expect(get.mock.calls[0][0]).toBe(archives[arch].url)
    expect(get.mock.calls[0][1]).toEqual({
      headers: { Range: archives[arch].range, "Accept-Encoding": "identity" },
      maxHeaderSize: 8192,
    })
  })

  it("accepts an explicitly unencoded response", async () => {
    exchange(arch, { headers: { "content-encoding": "identity" } })
    await expect(fetchAlpineZlibArchive(arch)).resolves.toHaveLength(archives[arch].size)
  })

  it.each([
    ["full response", { status: 200 }],
    ["not found", { status: 404 }],
    ["redirect", { status: 302, headers: { location: "https://other.invalid/" } }],
    ["missing range", { headers: { "content-range": undefined } }],
    ["wrong range", { headers: { "content-range": "bytes 0-1/2" } }],
    ["missing length", { headers: { "content-length": undefined } }],
    ["wrong length", { headers: { "content-length": "1" } }],
    ["encoded response", { headers: { "content-encoding": "gzip" } }],
  ])("rejects a %s before reading body bytes", async (_name, options) => {
    const { get, response } = exchange(arch, options)
    await expect(fetchAlpineZlibArchive(arch)).rejects.toThrow()
    expect(response.destroy).toHaveBeenCalledOnce()
    expect(get).toHaveBeenCalledOnce()
  })

  it.each([
    "overrun",
    "short",
    "end-incomplete",
    "non-buffer",
    "read-error",
    "closed",
    "aborted",
    "request-error",
  ])("rejects %s without producing an archive", async (outcome) => {
    const { get } = exchange(arch, { outcome })
    await expect(fetchAlpineZlibArchive(arch)).rejects.toThrow()
    expect(get).toHaveBeenCalledOnce()
  })
})

it.each(["", "armv7", "../x86_64", "__proto__"])(
  "rejects unsupported architecture %s before making a request",
  async (arch) => {
    const get = vi.spyOn(https, "get")
    await expect(fetchAlpineZlibArchive(arch)).rejects.toThrow(/architecture/i)
    expect(get).not.toHaveBeenCalled()
  }
)

it.each(["stall", "no-response"])(
  "destroys a %s request at the bounded deadline",
  async (outcome) => {
    vi.useFakeTimers()
    const { request, response } = exchange("x86_64", { outcome })
    const result = expect(fetchAlpineZlibArchive("x86_64")).rejects.toThrow(/timed out/i)
    await vi.advanceTimersByTimeAsync(18000)
    await result
    expect(request.destroy).toHaveBeenCalledOnce()
    expect(response.destroy).toHaveBeenCalledTimes(outcome === "stall" ? 1 : 0)
  }
)

it("rejects a synchronous HTTPS failure", async () => {
  const get = vi.spyOn(https, "get").mockImplementation(() => {
    throw new Error("synthetic transport failure")
  })
  await expect(fetchAlpineZlibArchive("x86_64")).rejects.toThrow(/transport failure/)
  expect(get).toHaveBeenCalledOnce()
})

const cliBootstrap = `
import { EventEmitter } from "node:events"
import fs from "node:fs"
import https from "node:https"
import { syncBuiltinESMExports } from "node:module"

const scenario = process.env.UE_ZLIB_TEST_SCENARIO
let writes = 0
fs.promises.writeFile = async (target, bytes, options) => {
  if (scenario === "write-error") throw new Error("synthetic write failure")
  writes += 1
  process.stdout.write(JSON.stringify({ writes, target, length: bytes.length, mode: options.mode }) + "\\n")
}
if (scenario === "timeout" || scenario === "response-timeout") {
  const realSetTimeout = globalThis.setTimeout
  globalThis.setTimeout = (callback, milliseconds) => {
    if (milliseconds !== 18000) throw new Error("unexpected deadline")
    return realSetTimeout(callback, 10)
  }
}
https.get = (_url, _options, callback) => {
  if (scenario === "sync-error") throw new Error("synthetic transport failure")
  const request = new EventEmitter()
  request.destroy = () => {}
  process.nextTick(() => {
    if (scenario === "request-error") {
      request.emit("error", new Error("synthetic request failure"))
      return
    }
    if (scenario === "timeout") return
    const arm = process.argv[2] === "aarch64"
    const size = arm ? 54334 : 56210
    const response = new EventEmitter()
    response.statusCode = scenario === "bad-status" ? 200 : 206
    response.headers = {
      "content-range": arm ? "bytes 16148480-16202813/93452288" : "bytes 15585280-15641489/70254592",
      "content-length": String(size),
    }
    if (scenario === "bad-range") response.headers["content-range"] = "bytes 0-1/2"
    if (scenario === "bad-length") response.headers["content-length"] = "1"
    if (scenario === "bad-encoding") response.headers["content-encoding"] = "gzip"
    if (scenario === "identity-encoding") response.headers["content-encoding"] = "identity"
    response.complete = false
    response.destroyed = false
    response.destroy = () => { response.destroyed = true }
    callback(response)
    if (response.destroyed || scenario === "response-timeout") return
    const first = Math.floor(size / 2)
    response.emit("data", Buffer.alloc(first, 97))
    if (scenario === "read-error") { response.emit("error", new Error("synthetic read failure")); return }
    if (scenario === "closed") { response.emit("close"); return }
    if (scenario === "aborted") { response.emit("aborted"); return }
    if (scenario === "non-buffer") { response.emit("data", "not a buffer"); return }
    const rest = size - first + (scenario === "overrun" ? 1 : scenario === "short" ? -1 : 0)
    response.emit("data", Buffer.alloc(rest, 98))
    if (scenario === "overrun") {
      response.emit("data", Buffer.from("ignored"))
      response.emit("error", new Error("late synthetic read failure"))
    }
    response.complete = scenario !== "end-incomplete"
    response.emit("end")
    if (response.complete) response.emit("close")
  })
  return request
}
syncBuiltinESMExports()
`

function runCli(scenario, args) {
  const preload = `data:text/javascript;base64,${Buffer.from(cliBootstrap).toString("base64")}`
  const helper = resolve("scripts/fetch-alpine-zlib-archive.mjs")
  return spawnSync(process.execPath, ["--import", preload, helper, ...args], {
    encoding: "utf8",
    env: {
      UE_ZLIB_TEST_SCENARIO: scenario,
      ...(process.env.SystemRoot ? { SystemRoot: process.env.SystemRoot } : {}),
    },
    timeout: 5000,
    maxBuffer: 4096,
  })
}

it.each([
  ["x86_64", 56210],
  ["aarch64", 54334],
])("CLI writes the completed %s range exactly once", (arch, size) => {
  const result = runCli("valid", [arch])
  expect(result.error).toBeUndefined()
  expect(result.status).toBe(0)
  expect(result.stderr).toBe("")
  expect(JSON.parse(result.stdout)).toEqual({
    writes: 1,
    target: "/tmp/zlib.apk",
    length: size,
    mode: 0o600,
  })
})

it("CLI accepts an identity-encoded response", () => {
  const result = runCli("identity-encoding", ["x86_64"])
  expect(result.error).toBeUndefined()
  expect(result.status).toBe(0)
  expect(JSON.parse(result.stdout).writes).toBe(1)
})

it.each([
  ["missing argument", "valid", []],
  ["extra argument", "valid", ["x86_64", "extra"]],
  ["unsupported architecture", "valid", ["armv7"]],
  ["transport failure", "request-error", ["x86_64"]],
  ["synchronous transport failure", "sync-error", ["x86_64"]],
  ["invalid response", "bad-status", ["x86_64"]],
  ["wrong range", "bad-range", ["x86_64"]],
  ["wrong length", "bad-length", ["x86_64"]],
  ["encoded response", "bad-encoding", ["x86_64"]],
  ["request timeout", "timeout", ["x86_64"]],
  ["response timeout", "response-timeout", ["x86_64"]],
  ["read failure", "read-error", ["x86_64"]],
  ["closed response", "closed", ["x86_64"]],
  ["aborted response", "aborted", ["x86_64"]],
  ["non-buffer response", "non-buffer", ["x86_64"]],
  ["overlong response", "overrun", ["x86_64"]],
  ["short response", "short", ["x86_64"]],
  ["incomplete end", "end-incomplete", ["x86_64"]],
  ["write failure", "write-error", ["x86_64"]],
])("CLI exits nonzero without a write on %s", (_name, scenario, args) => {
  const result = runCli(scenario, args)
  expect(result.error).toBeUndefined()
  expect(result.status).toBe(1)
  expect(result.stdout).toBe("")
  expect(result.stderr).toContain("Unable to fetch the pinned Alpine archive")
})
