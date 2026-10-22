import { createTrustedScriptURL } from "@/utils/trustedTypes"

let modulePromise: ReturnType<typeof importMapLibre> | undefined
let installedWorkerUrl: string | undefined
let installedWorkerProxy: typeof Worker | undefined

function installTrustedMapLibreWorker(workerUrl: string): void {
  if (typeof window === "undefined") return

  let resolvedUrl: URL
  try {
    resolvedUrl = new URL(workerUrl, window.location.href)
  } catch {
    throw new TypeError("MapLibre worker must be a same-origin static .mjs asset")
  }
  if (
    resolvedUrl.origin !== window.location.origin ||
    !resolvedUrl.pathname.endsWith(".mjs") ||
    resolvedUrl.username ||
    resolvedUrl.password ||
    resolvedUrl.search ||
    resolvedUrl.hash
  ) {
    throw new TypeError("MapLibre worker must be a same-origin static .mjs asset")
  }

  if (installedWorkerUrl === workerUrl && globalThis.Worker === installedWorkerProxy) return

  const nativeWorker = globalThis.Worker
  if (typeof nativeWorker !== "function") {
    throw new TypeError("MapLibre requires the browser Worker constructor")
  }

  // MapLibre requires a string URL for its .endsWith and origin checks. Upgrade
  // only its exact Vite .mjs asset at the native Worker sink, where Trusted Types
  // is enforced, and leave every other application Worker call unchanged.
  const trustedWorker = new Proxy(nativeWorker, {
    construct(target, argumentsList, newTarget) {
      const [requestedUrl, options] = argumentsList as [unknown, WorkerOptions?]
      if (requestedUrl !== workerUrl || options?.type !== "module") {
        return Reflect.construct(target, argumentsList, newTarget)
      }

      const trustedUrl = createTrustedScriptURL(workerUrl) as unknown as string
      return Reflect.construct(target, [trustedUrl, ...argumentsList.slice(1)], newTarget)
    },
  })

  globalThis.Worker = trustedWorker
  installedWorkerUrl = workerUrl
  installedWorkerProxy = trustedWorker
}

async function importMapLibre() {
  const [mapModule, maplibre, workerAsset] = await Promise.all([
    import("@/components/map/MapLibreMap"),
    import("maplibre-gl"),
    import("maplibre-gl/dist/maplibre-gl-worker.mjs?url"),
  ])
  installTrustedMapLibreWorker(workerAsset.default)
  maplibre.setWorkerUrl(workerAsset.default)
  return { default: mapModule.MapLibreMapComponent }
}

/** Shared loader used by route intent preloading and React.lazy rendering. */
export function loadMapLibre() {
  modulePromise ??= importMapLibre().catch((error: unknown) => {
    modulePromise = undefined
    throw error
  })
  return modulePromise
}
