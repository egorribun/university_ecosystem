/**
 * @vitest-environment node
 */
import { afterEach, beforeEach, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  init: vi.fn(),
  hmacSha256Sign: vi.fn(),
  hmacSha256SignBase64: vi.fn(),
}))

vi.mock("../../../rust-crypto/pkg/uni_wasm_crypto.js", () => ({
  default: mocks.init,
  pbkdf2_derive: vi.fn(),
  scrypt_derive: vi.fn(),
  hmac_sha256_sign: mocks.hmacSha256Sign,
  hmac_sha256_sign_base64: mocks.hmacSha256SignBase64,
}))

type WorkerScope = {
  onmessage: ((event: MessageEvent) => Promise<void>) | null
  postMessage: ReturnType<typeof vi.fn>
}

let scope: WorkerScope

beforeEach(async () => {
  vi.resetModules()
  vi.resetAllMocks()
  mocks.init.mockResolvedValue(undefined)
  mocks.hmacSha256Sign.mockReturnValue("!")
  scope = { onmessage: null, postMessage: vi.fn() }
  vi.stubGlobal("self", scope)
  await import("../crypto.worker")
})

afterEach(() => {
  vi.unstubAllGlobals()
})

it("returns the concrete WASM HMAC error in the worker error envelope", async () => {
  mocks.hmacSha256SignBase64.mockImplementationOnce(() => {
    throw new Error("WASM HMAC failed")
  })
  await scope.onmessage?.({
    data: {
      type: "HMAC_SHA256",
      id: 41,
      payload: { key: "key", json: "payload" },
    },
  } as MessageEvent)

  expect(scope.postMessage).toHaveBeenCalledWith({
    id: 41,
    error: "WASM HMAC failed",
  })
})

it("returns the WASM base64 result without a JavaScript encoding round trip", async () => {
  const expected = Buffer.from("00".repeat(32), "hex").toString("base64")
  mocks.hmacSha256Sign.mockReturnValue("00".repeat(32))
  mocks.hmacSha256SignBase64.mockReturnValue(expected)
  vi.stubGlobal("btoa", () => {
    throw new Error("JavaScript HMAC encoding must not be used")
  })
  await scope.onmessage?.({
    data: { type: "HMAC_SHA256", id: 42, payload: { key: "key", json: "payload" } },
  } as MessageEvent)

  expect(scope.postMessage).toHaveBeenCalledWith({ id: 42, result: expected })
  expect(mocks.hmacSha256SignBase64).toHaveBeenCalledWith("key", "payload")
  expect(mocks.hmacSha256Sign).not.toHaveBeenCalled()
})

it("initialises the WASM module once and reuses it for later messages", async () => {
  mocks.hmacSha256SignBase64.mockReturnValue("sig")

  for (const id of [1, 2]) {
    await scope.onmessage?.({
      data: { type: "HMAC_SHA256", id, payload: { key: "key", json: "payload" } },
    } as MessageEvent)
  }

  expect(mocks.init).toHaveBeenCalledOnce()
  expect(scope.postMessage.mock.calls).toStrictEqual([
    [{ id: 1, result: "sig" }],
    [{ id: 2, result: "sig" }],
  ])
})

it("does not sign before WASM initialisation has completed", async () => {
  let finishInit: () => void = () => undefined
  mocks.init.mockReturnValueOnce(
    new Promise<void>((resolve) => {
      finishInit = resolve
    })
  )
  mocks.hmacSha256SignBase64.mockReturnValue("sig")

  const handled = scope.onmessage?.({
    data: { type: "HMAC_SHA256", id: 3, payload: { key: "key", json: "payload" } },
  } as MessageEvent)
  await Promise.resolve()
  expect(mocks.hmacSha256SignBase64).not.toHaveBeenCalled()

  finishInit()
  await handled
  expect(scope.postMessage).toHaveBeenCalledWith({ id: 3, result: "sig" })
})

it("retries WASM initialisation on the next request after a shared failure", async () => {
  let rejectInit: (reason: Error) => void = () => undefined
  mocks.init.mockReturnValueOnce(
    new Promise<void>((_resolve, reject) => {
      rejectInit = reject
    })
  )
  mocks.hmacSha256SignBase64.mockReturnValue("recovered")

  const dispatch = (id: number) =>
    scope.onmessage?.({
      data: { type: "HMAC_SHA256", id, payload: { key: "key", json: "payload" } },
    } as MessageEvent)

  const first = dispatch(51)
  const second = dispatch(52)
  expect(mocks.init).toHaveBeenCalledOnce()
  expect(mocks.hmacSha256SignBase64).not.toHaveBeenCalled()
  rejectInit(new Error("WASM download interrupted"))
  await Promise.all([first, second])

  expect(scope.postMessage.mock.calls).toStrictEqual([
    [{ id: 51, error: "WASM download interrupted" }],
    [{ id: 52, error: "WASM download interrupted" }],
  ])
  expect(mocks.hmacSha256SignBase64).not.toHaveBeenCalled()

  let finishRetry: () => void = () => undefined
  mocks.init.mockReturnValueOnce(
    new Promise<void>((resolve) => {
      finishRetry = resolve
    })
  )
  const third = dispatch(53)
  const fourth = dispatch(54)
  expect(mocks.init).toHaveBeenCalledTimes(2)
  expect(mocks.hmacSha256SignBase64).not.toHaveBeenCalled()

  finishRetry()
  await Promise.all([third, fourth])
  await dispatch(55)

  expect(mocks.init).toHaveBeenCalledTimes(2)
  expect(mocks.hmacSha256SignBase64).toHaveBeenCalledTimes(3)
  expect(scope.postMessage.mock.calls.slice(2)).toStrictEqual([
    [{ id: 53, result: "recovered" }],
    [{ id: 54, result: "recovered" }],
    [{ id: 55, result: "recovered" }],
  ])
})

it("does not reload an initialised module after an operation error", async () => {
  mocks.hmacSha256SignBase64
    .mockImplementationOnce(() => {
      throw new Error("Invalid operation input")
    })
    .mockReturnValueOnce("next-result")

  for (const id of [61, 62]) {
    await scope.onmessage?.({
      data: { type: "HMAC_SHA256", id, payload: { key: "key", json: "payload" } },
    } as MessageEvent)
  }

  expect(mocks.init).toHaveBeenCalledOnce()
  expect(scope.postMessage.mock.calls).toStrictEqual([
    [{ id: 61, error: "Invalid operation input" }],
    [{ id: 62, result: "next-result" }],
  ])
})

it("keeps failed WASM initialisation attempts retryable until one succeeds", async () => {
  mocks.init
    .mockRejectedValueOnce(new Error("First download failed"))
    .mockRejectedValueOnce(new Error("Second download failed"))
    .mockResolvedValueOnce(undefined)
  mocks.hmacSha256SignBase64.mockReturnValue("third-result")

  for (const id of [71, 72, 73]) {
    await scope.onmessage?.({
      data: { type: "HMAC_SHA256", id, payload: { key: "key", json: "payload" } },
    } as MessageEvent)
  }

  expect(mocks.init).toHaveBeenCalledTimes(3)
  expect(mocks.hmacSha256SignBase64).toHaveBeenCalledOnce()
  expect(scope.postMessage.mock.calls).toStrictEqual([
    [{ id: 71, error: "First download failed" }],
    [{ id: 72, error: "Second download failed" }],
    [{ id: 73, result: "third-result" }],
  ])
})
