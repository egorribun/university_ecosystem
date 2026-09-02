import assert from "node:assert/strict"
import test from "node:test"

import { mapLibreWorkerAssets } from "./maplibre-worker-assets.mjs"

test("emits the MapLibre worker sibling under its runtime import name", () => {
  const emitted = []
  const plugin = mapLibreWorkerAssets({ readSharedModule: () => "shared-module" })

  plugin.generateBundle.call({ emitFile: (asset) => emitted.push(asset) })

  assert.deepEqual(emitted, [
    {
      type: "asset",
      fileName: "assets/maplibre-gl-shared.mjs",
      source: "shared-module",
    },
  ])
})
