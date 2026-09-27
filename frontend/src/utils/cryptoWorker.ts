/**
 * Crypto Worker Wrapper
 *
 * Bridges the main thread to the Web Crypto API worker.
 * Offloads all heavy cryptographic operations to a separate thread.
 */

// Worker instance
const worker =
  typeof Worker !== "undefined"
    ? new Worker(new URL("../workers/crypto.worker.ts", import.meta.url), {
        type: "module",
      })
    : ({
        postMessage: () => {},
      } as unknown as Worker)

// Promise handling
interface WorkerMessage {
  id: string
  result?: unknown
  error?: string
}

type PendingEntry = { resolve: (val: unknown) => void; reject: (err: Error) => void }
// Every entry removes itself (and its timeout) as soon as it settles.
const pendingPromises = new Map<string, PendingEntry>()

/** Number of requests still waiting for the worker; lets tests prove settled requests are released. */
export function getPendingCryptoRequestCountForTesting(): number {
  return pendingPromises.size
}

// FE-01 (audit 2026-03-08 Wave 5): Drain all pending promises when the worker
// crashes (OOM, uncaught exception) so callers receive a rejection rather than
// hanging forever. Without this, scrypt / PBKDF2 calls block indefinitely
// if the worker thread dies unexpectedly.
worker.onerror = (event: ErrorEvent) => {
  const err = new Error(`Crypto worker crashed: ${event.message ?? "unknown error"}`)
  for (const { reject } of pendingPromises.values()) {
    reject(err)
  }
}

worker.onmessage = (event: MessageEvent<WorkerMessage>) => {
  const msg = event.data
  // Guard against empty messages; any other malformed message (e.g. from a
  // compromised worker) carries no id of a pending request and is ignored.
  if (!msg) return

  const { id, result, error } = msg
  const pending = pendingPromises.get(id)

  if (pending) {
    if (error) {
      pending.reject(new Error(error))
    } else {
      pending.resolve(result)
    }
  }
}

// FE-01 (audit 2026-03-08 Wave 5): 30-second timeout on every worker message.
// Scrypt with N=16384 takes ~5-20 s depending on hardware; 30 s provides
// headroom while still bounding worst-case hangs. Timeout clears on resolution.
const CRYPTO_WORKER_TIMEOUT_MS = 30_000

const post = <T, P = unknown>(type: string, payload: P): Promise<T> => {
  return new Promise((resolve, reject) => {
    const id = crypto.randomUUID()
    const release = () => {
      clearTimeout(timeoutId)
      pendingPromises.delete(id)
    }
    const entry: PendingEntry = {
      resolve: (val: unknown) => {
        release()
        resolve(val as T)
      },
      reject: (err: Error) => {
        release()
        reject(err)
      },
    }

    const timeoutId = setTimeout(() => {
      entry.reject(
        new Error(`Crypto worker timeout after ${CRYPTO_WORKER_TIMEOUT_MS}ms (op: ${type})`)
      )
    }, CRYPTO_WORKER_TIMEOUT_MS)

    pendingPromises.set(id, entry)

    try {
      worker.postMessage({ type, payload, id })
    } catch (error) {
      // A synchronous clone/dispatch failure never reaches a worker reply or timeout.
      release()
      reject(error)
    }
  })
}

// Interfaces matching the previous implementation for compatibility
interface Pbkdf2Params {
  value: string
  salt: string
  keySize: number
  iterations: number
}

interface ScryptParams {
  password: Uint8Array
  salt: Uint8Array
  N: number
  r: number
  p: number
  dkLen: number
}

interface HmacSha256Params {
  json: string
  key: string
}

export const cryptoWorker = {
  /**
   * PBKDF2 key derivation (via Worker)
   */
  async pbkdf2(params: Pbkdf2Params): Promise<string> {
    return post<string>("PBKDF2", params)
  },

  /**
   * Scrypt key derivation (via Worker - uses high-iter PBKDF2 shim)
   */
  async scrypt(params: ScryptParams): Promise<Uint8Array> {
    // We pass the raw parameters. The worker handles the re-mapping to PBKDF2
    const result = await post<number[]>("SCRYPT", params)
    return new Uint8Array(result)
  },

  /**
   * HMAC-SHA256 signing (via Worker)
   */
  async hmacSha256(params: HmacSha256Params): Promise<string> {
    return post<string>("HMAC_SHA256", params)
  },
}
