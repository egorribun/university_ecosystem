import initializeWasmSanitizer from "wasm-sanitizer"

let initialization: Promise<boolean> | undefined

/** Initialize the existing WASM package in browsers before synchronous APIs run. */
export const ensureWasmSanitizerInitialized = (): Promise<boolean> => {
  if (typeof window === "undefined") return Promise.resolve(false)
  if (initialization) return initialization

  const attempt = Promise.resolve().then(() => initializeWasmSanitizer())
  const shared = attempt.then(
    () => true,
    () => {
      initialization = undefined
      return false
    }
  )
  initialization = shared
  return shared
}
