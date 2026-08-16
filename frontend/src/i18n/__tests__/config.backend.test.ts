import { beforeEach, describe, expect, it, vi } from "vitest"
import type { BackendModule, ResourceKey } from "i18next"

const mocks = vi.hoisted(() => ({
  plugins: [] as unknown[],
  init: vi.fn(() => Promise.resolve()),
}))

vi.mock("i18next", () => {
  const instance = {
    use(plugin: unknown) {
      mocks.plugins.push(plugin)
      return instance
    },
    init: mocks.init,
  }
  return { default: instance }
})
vi.mock("react-i18next", () => ({ initReactI18next: { type: "3rdParty" } }))

describe("dynamic i18n backend", () => {
  beforeEach(() => {
    mocks.plugins.length = 0
    mocks.init.mockClear()
    vi.resetModules()
  })

  it("reports a missing locale file through the backend callback", async () => {
    const { dynamicBackend } = await import("@/i18n/config")
    dynamicBackend.init?.({} as never, {} as never, {} as never)

    const result = await new Promise<{ error: Error | null; resource: ResourceKey | null }>(
      (resolve) => {
        dynamicBackend.read("missing", "namespace", (error, resource) =>
          resolve({ error, resource })
        )
      }
    )

    expect(result.error?.message).toBe("Missing locale file for missing/namespace")
    expect(result.resource).toBeNull()
    expect(mocks.init).toHaveBeenCalledOnce()
    expect(mocks.plugins[0]).toBe(dynamicBackend as BackendModule)
  })

  it("loads every declared locale resource", async () => {
    const { dynamicBackend, localeLoaders, namespaces, supportedLngs } = await import(
      "@/i18n/config"
    )

    for (const language of supportedLngs) {
      for (const namespace of namespaces) {
        const result = await new Promise<{ error: Error | null; resource: ResourceKey | null }>(
          (resolve) => {
            dynamicBackend.read(language, namespace, (error, resource) =>
              resolve({ error, resource })
            )
          }
        )
        expect(result.error).toBeNull()
        expect(result.resource).not.toBeNull()
        expect(localeLoaders[`./locales/${language}/${namespace}.json`]).toBeTypeOf("function")
      }
    }
  })

  it("unwraps default resources and forwards loader failures", async () => {
    const { dynamicBackend, localeLoaders } = await import("@/i18n/config")
    const key = "./locales/en/common.json"
    const original = localeLoaders[key]!

    localeLoaders[key] = () => Promise.resolve({ default: { synthetic: "resource" } })
    const loaded = await new Promise<ResourceKey | null>((resolve, reject) => {
      dynamicBackend.read("en", "common", (error, resource) =>
        error ? reject(error) : resolve(resource)
      )
    })
    expect(loaded).toEqual({ synthetic: "resource" })

    const failure = new Error("loader failed")
    localeLoaders[key] = () => Promise.reject(failure)
    const received = await new Promise<Error | null>((resolve) => {
      dynamicBackend.read("en", "common", (error) => resolve(error))
    })
    expect(received).toBe(failure)
    localeLoaders[key] = original
  })
})
