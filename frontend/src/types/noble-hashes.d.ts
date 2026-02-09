declare module "@noble/hashes/hmac" {
  type Input = Uint8Array | string
  type HashFn = ((message: Uint8Array | string) => Uint8Array) & {
    outputLen?: number
    blockLen?: number
  }

  export function hmac(hash: HashFn, key: Input, message: Input): Uint8Array
}

declare module "@noble/hashes/sha256" {
  type Input = Uint8Array | string

  export function sha256(message: Input): Uint8Array
}




