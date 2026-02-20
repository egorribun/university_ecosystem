/**
 * Crypto Worker Wrapper
 *
 * Bridges the main thread to the Web Crypto API worker.
 * Offloads all heavy cryptographic operations to a separate thread.
 */

// Worker instance
const worker = (typeof Worker !== "undefined")
  ? new Worker(new URL("../workers/crypto.worker.ts", import.meta.url), {
      type: "module",
    })
  : ({
      postMessage: () => {},
      onmessage: () => {},
    } as unknown as Worker)

// Promise handling
interface WorkerMessage {
  id: string
  result?: unknown
  error?: string
}

const pendingPromises = new Map<string, { resolve: (val: unknown) => void; reject: (err: Error) => void }>()

worker.onmessage = (event: MessageEvent<WorkerMessage>) => {
  const { id, result, error } = event.data
  const pending = pendingPromises.get(id)

  if (pending) {
    if (error) {
      pending.reject(new Error(error))
    } else {
      pending.resolve(result)
    }
    pendingPromises.delete(id)
  }
}

const post = <T, P = unknown>(type: string, payload: P): Promise<T> => {
  return new Promise((resolve, reject) => {
    const id = crypto.randomUUID()
    pendingPromises.set(id, { resolve: resolve as (val: unknown) => void, reject })
    worker.postMessage({ type, payload, id })
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

