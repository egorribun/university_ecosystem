import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"

const sharedModulePath = fileURLToPath(
  new URL("../node_modules/maplibre-gl/dist/maplibre-gl-shared.mjs", import.meta.url)
)

/**
 * MapLibre's production worker is a small ESM entry that imports the sibling
 * `maplibre-gl-shared.mjs` module by its stable name. Vite's `?url` handling
 * emits the worker but does not emit that sibling dependency, so the worker
 * otherwise fails at runtime with a 404. Keep the worker URL fingerprinted and
 * emit only its version-pinned sibling under the relative name it imports.
 */
export function mapLibreWorkerAssets({
  readSharedModule = () => readFileSync(sharedModulePath),
} = {}) {
  return {
    name: "maplibre-worker-shared-asset",
    apply: "build",
    generateBundle() {
      this.emitFile({
        type: "asset",
        fileName: "assets/maplibre-gl-shared.mjs",
        source: readSharedModule(),
      })
    },
  }
}
