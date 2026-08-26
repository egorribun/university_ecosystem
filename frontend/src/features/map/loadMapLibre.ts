let modulePromise: ReturnType<typeof importMapLibre> | undefined

async function importMapLibre() {
  const [mapModule, maplibre, workerAsset] = await Promise.all([
    import("@/components/map/MapLibreMap"),
    import("maplibre-gl"),
    import("maplibre-gl/dist/maplibre-gl-worker.mjs?url"),
  ])
  maplibre.setWorkerUrl(workerAsset.default)
  return mapModule
}

/** Shared loader used by route intent preloading and React.lazy rendering. */
export function loadMapLibre() {
  modulePromise ??= importMapLibre().catch((error: unknown) => {
    modulePromise = undefined
    throw error
  })
  return modulePromise
}
