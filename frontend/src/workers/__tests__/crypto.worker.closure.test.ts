/**
 * @vitest-environment node
 */
import { afterEach, beforeEach, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  init: vi.fn(),
  hmacSha256Sign: vi.fn(),
}))

vi.mock("../../../rust-crypto/pkg/uni_wasm_crypto.js", () => ({
  default: mocks.init,
  pbkdf2_derive: vi.fn(),
  scrypt_derive: vi.fn(),
  hmac_sha256_sign: mocks.hmacSha256Sign,
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

it("returns the concrete WASM validation error for malformed HMAC hex", async () => {
  await scope.onmessage?.({
    data: {
      type: "HMAC_SHA256",
      id: 41,
      payload: { key: "key", json: "payload" },
    },
  } as MessageEvent)

  expect(scope.postMessage).toHaveBeenCalledWith({
    id: 41,
    error: "Invalid hex from WASM HMAC",
  })
})
