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
  vi.clearAllMocks()
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
