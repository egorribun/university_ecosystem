import { existsSync, readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

import vitestConfig from "../../../vitest.config"

/**
 * AUD-399 / AUD-400: vitest.config.ts is the only Vitest configuration that
 * runs. A second `test` block or workbox rule in vite.config.mts is never
 * loaded, so it must not survive as apparent behaviour.
 */
const viteConfigSource = readFileSync(resolve(process.cwd(), "vite.config.mts"), "utf8")

describe("canonical Vitest configuration", () => {
  it("loads the one setup file that the canonical config names", () => {
    expect(vitestConfig.test?.setupFiles).toEqual(["src/setupTests.ts"])
    expect(existsSync(resolve(process.cwd(), "src/setupTests.ts"))).toBe(true)
  })

  it("keeps no second setup file that nothing loads", () => {
    expect(existsSync(resolve(process.cwd(), "src/test/setup.ts"))).toBe(false)
  })

  it("keeps no shadowed test block in vite.config.mts", () => {
    expect(viteConfigSource).not.toMatch(/^\s{4}test:\s*\{/mu)
    expect(viteConfigSource).not.toMatch(/setupFiles:\s*"\.\/src\/test\/setup\.ts"/u)
  })

  it("keeps no workbox runtimeCaching rule under the injectManifest strategy", () => {
    // injectManifest ignores `workbox.*`; API caching lives in src/sw/api.ts.
    expect(viteConfigSource).not.toMatch(/runtimeCaching/u)
    expect(viteConfigSource).not.toMatch(/\/api\/\(news\|schedule\|events\)/u)
  })
})
