const DEFAULT_BACKEND_ORIGIN = "http://localhost:8000"

type NodeProcessLike = {
  env?: Record<string, string | undefined>
}

/**
 * Resolve the backend origin used only by the Node SSR runtime.
 *
 * VITE_BACKEND_ORIGIN remains the build-time fallback for static assets and
 * older images. BACKEND_ORIGIN is read at runtime so one immutable frontend
 * image can be deployed under arbitrary Compose/Helm service names.
 */
export function resolveSsrBackendOrigin(): string {
  const runtimeProcess = (globalThis as typeof globalThis & { process?: NodeProcessLike }).process
  const runtimeOrigin =
    typeof window === "undefined" ? runtimeProcess?.env?.BACKEND_ORIGIN?.trim() : undefined
  const buildOrigin = import.meta.env?.VITE_BACKEND_ORIGIN?.trim()
  return (runtimeOrigin || buildOrigin || DEFAULT_BACKEND_ORIGIN).replace(/\/+$/u, "")
}
