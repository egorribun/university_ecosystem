type NodeProcessLike = {
  env?: Record<string, string | undefined>
}

function trimOrigin(value: string | undefined): string | undefined {
  return typeof value === "string" ? value.trim() : undefined
}

/**
 * Resolve the backend origin used only by the Node SSR runtime.
 *
 * VITE_BACKEND_ORIGIN remains the build-time fallback for static assets and
 * older images. BACKEND_ORIGIN is read at runtime so one immutable frontend
 * image can be deployed under arbitrary Compose/Helm service names.
 */
export function resolveSsrBackendOrigin(): string {
  const defaultBackendOrigin = "http://localhost:8000"
  // Wrapping the optional Node process in Object() keeps the environment read
  // total in browser/jsdom/Vitest runtimes. That is important for SSR/client
  // module evaluation: a missing process must fall back, never throw or hold a
  // request open while a mutation runner explores a guard branch.
  const runtimeProcess = Object(
    (globalThis as typeof globalThis & { process?: NodeProcessLike }).process
  ) as NodeProcessLike
  const runtimeEnv = Object(runtimeProcess.env) as Record<string, unknown>
  const runtimeOrigin =
    typeof window === "undefined"
      ? trimOrigin(runtimeEnv.BACKEND_ORIGIN as string | undefined)
      : undefined

  // Vite always provides import.meta.env in every supported browser/SSR build.
  const buildOrigin = trimOrigin(import.meta.env.VITE_BACKEND_ORIGIN)
  return (runtimeOrigin || buildOrigin || defaultBackendOrigin).replace(/\/+$/u, "")
}
