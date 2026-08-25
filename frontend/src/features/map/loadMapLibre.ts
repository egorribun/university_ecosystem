let modulePromise: ReturnType<typeof importMapLibre> | undefined

function importMapLibre() {
  return import("@/components/map/MapLibreMap")
}

/** Shared loader used by route intent preloading and React.lazy rendering. */
export function loadMapLibre() {
  modulePromise ??= importMapLibre().catch((error: unknown) => {
    modulePromise = undefined
    throw error
  })
  return modulePromise
}
