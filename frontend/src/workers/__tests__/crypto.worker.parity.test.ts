// @vitest-environment node
/**
 * crypto.worker.ts ↔ WASM parity KATs (testing session 10, Stream D).
 *
 * Drives the worker's message protocol end-to-end against the REAL
 * uni_wasm_crypto WASM build and asserts byte-exact parity with the RFC
 * vectors cross-validated in frontend/rust-crypto/src/lib.rs (session 9):
 * PBKDF2 RFC 7914 §11, HMAC RFC 4231 TC1/TC2, scrypt RFC 7914 §12 V1/V2.
 *
 * Mechanics:
 * - `initSync({ module: bytes })` pre-initializes the wasm-bindgen glue from
 *   disk BEFORE the worker module loads; the glue caches the instance
 *   (`if (wasm !== undefined) return wasm` — pkg/uni_wasm_crypto.js:240,261),
 *   so the worker's own no-arg `init()` resolves from cache and never attempts
 *   a fetch() (which would fail for file URLs under Node).
 * - `globalThis.self` is stubbed BEFORE the dynamic worker import so the
 *   module-scope `self.onmessage =` assignment lands on our capture object
 *   (a static import would hoist above the stub and crash).
 * - Coverage note: src/workers/** is coverage-excluded by design — this is a
 *   parity/regression wave, not a gate mover.
 *
 * NEVER pass N=0 to SCRYPT (n.ilog2() panics in the wasm — unrecoverable).
 */

import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import path from "node:path"
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest"

// RFC vectors — copied verbatim from frontend/rust-crypto/src/lib.rs:47-58
// (cross-validated against the RustCrypto reference impls in session 9).
const PBKDF2_PASSWD_SALT_C1 =
  "55ac046e56e3089fec1691c22544b605f94185216dde0465e68b9d57c20dacbc49ca9cccf179b645991664b39d77ef317c71b845b1e30bd509112041d3a19783" // pragma: allowlist secret
const HMAC_TC1 = "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7" // pragma: allowlist secret
const HMAC_TC2 = "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843" // pragma: allowlist secret
const SCRYPT_V1 =
  "77d6576238657b203b19ca42c18a0497f16b4844e3074ae8dfdffa3fede21442fcd0069ded0948f8326a753a0fc81f17e8d3e0fb2e0d3628cf35e20c38d18906" // pragma: allowlist secret
const SCRYPT_V2 =
  "fdbabe1c9d3472007856e7190d01e9fe7c6ad7cbc8237830e77376634b3731622eaf30d92e22a3886ff109279d9830dac727afb94a83ee6d8360cbdfa2cc0640" // pragma: allowlist secret

type WorkerMessage = { id: number; result?: unknown; error?: string }

const fakeSelf: {
  onmessage: ((event: { data: unknown }) => Promise<void> | void) | null
  postMessage: ReturnType<typeof vi.fn>
} = {
  onmessage: null,
  postMessage: vi.fn(),
}

async function dispatch(data: unknown): Promise<WorkerMessage | undefined> {
  fakeSelf.postMessage.mockClear()
  if (!fakeSelf.onmessage) throw new Error("worker onmessage was not registered")
  await fakeSelf.onmessage({ data })
  return fakeSelf.postMessage.mock.calls.at(-1)?.[0] as WorkerMessage | undefined
}

beforeAll(async () => {
  const here = path.dirname(fileURLToPath(import.meta.url))
  const wasmPath = path.resolve(here, "../../../rust-crypto/pkg/uni_wasm_crypto_bg.wasm")
  const glue = await import("../../../rust-crypto/pkg/uni_wasm_crypto.js")
  glue.initSync({ module: readFileSync(wasmPath) })

  vi.stubGlobal("self", fakeSelf)
  await import("../crypto.worker")
  expect(fakeSelf.onmessage).toBeTypeOf("function")
})

afterAll(() => {
  vi.unstubAllGlobals()
})

describe("crypto.worker PBKDF2 parity", () => {
  it("matches the RFC 7914 §11 PBKDF2-HMAC-SHA-256 vector (keySize in BITS)", async () => {
    const msg = await dispatch({
      type: "PBKDF2",
      id: 1,
      payload: { value: "passwd", salt: "salt", iterations: 1, keySize: 512 },
    })
    expect(msg).toEqual({ id: 1, result: PBKDF2_PASSWD_SALT_C1 })
  })

  it("derives keySize/8 bytes (256 bits → 64 hex chars)", async () => {
    const msg = await dispatch({
      type: "PBKDF2",
      id: 2,
      payload: { value: "pw", salt: "salt", iterations: 2, keySize: 256 },
    })
    expect(typeof msg?.result).toBe("string")
    expect((msg?.result as string).length).toBe(64)
  })
})

describe("crypto.worker HMAC-SHA256 parity", () => {
  it("matches RFC 4231 TC1 as base64 of the KAT hex", async () => {
    const msg = await dispatch({
      type: "HMAC_SHA256",
      id: 3,
      payload: { key: String.fromCharCode(0x0b).repeat(20), json: "Hi There" },
    })
    expect(msg).toEqual({
      id: 3,
      result: Buffer.from(HMAC_TC1, "hex").toString("base64"),
    })
  })

  it("matches RFC 4231 TC2 as base64 of the KAT hex", async () => {
    const msg = await dispatch({
      type: "HMAC_SHA256",
      id: 4,
      payload: { key: "Jefe", json: "what do ya want for nothing?" },
    })
    expect(msg).toEqual({
      id: 4,
      result: Buffer.from(HMAC_TC2, "hex").toString("base64"),
    })
  })
})

describe("crypto.worker SCRYPT parity", () => {
  it("matches RFC 7914 §12 vector 1 (N=16) as a plain number array", async () => {
    const msg = await dispatch({
      type: "SCRYPT",
      id: 5,
      payload: {
        password: new Uint8Array(0),
        salt: new Uint8Array(0),
        N: 16,
        r: 1,
        p: 1,
        dkLen: 64,
      },
    })
    expect(msg?.id).toBe(5)
    expect(msg?.result).toEqual(Array.from(Buffer.from(SCRYPT_V1, "hex")))
  })

  it("matches RFC 7914 §12 vector 2 (N=1024, r=8, p=16)", { timeout: 30_000 }, async () => {
    const msg = await dispatch({
      type: "SCRYPT",
      id: 6,
      payload: {
        password: new TextEncoder().encode("password"),
        salt: new TextEncoder().encode("NaCl"),
        N: 1024,
        r: 8,
        p: 16,
        dkLen: 64,
      },
    })
    expect(msg?.result).toEqual(Array.from(Buffer.from(SCRYPT_V2, "hex")))
  })

  it("invalid params (r=0) surface the worker's error envelope", async () => {
    const msg = await dispatch({
      type: "SCRYPT",
      id: 7,
      payload: {
        password: new Uint8Array(0),
        salt: new Uint8Array(0),
        N: 16,
        r: 0,
        p: 1,
        dkLen: 64,
      },
    })
    // wasm-bindgen throws the JsValue as a raw JS STRING — the worker's
    // `error instanceof Error` check is false → generic envelope message.
    expect(msg).toEqual({ id: 7, error: "Unknown worker error" })
  })
})

describe("crypto.worker protocol edges", () => {
  it("unknown message type posts nothing", async () => {
    const msg = await dispatch({ type: "NOPE", id: 8, payload: {} })
    expect(msg).toBeUndefined()
    expect(fakeSelf.postMessage).not.toHaveBeenCalled()
  })

  it("passes the request id through on success", async () => {
    const msg = await dispatch({
      type: "PBKDF2",
      id: 999,
      payload: { value: "a", salt: "b", iterations: 1, keySize: 256 },
    })
    expect(msg?.id).toBe(999)
  })
})
