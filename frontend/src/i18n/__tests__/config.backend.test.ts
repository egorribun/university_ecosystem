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

type BackendReadResult = {
  error: Error | null
  resource: ResourceKey | null
}

const readBackend = (backend: BackendModule, language: string, namespace: string) =>
  new Promise<BackendReadResult>((resolve, reject) => {
    backend.read(language, namespace, (error, resource) => {
      if (typeof resource === "boolean") {
        reject(new TypeError("Backend returned a retry signal instead of a locale resource"))
        return
      }
      resolve({
        error: typeof error === "string" ? new Error(error) : (error ?? null),
        resource: resource ?? null,
      })
    })
  })

describe("dynamic i18n backend", () => {
  beforeEach(() => {
    mocks.plugins.length = 0
    mocks.init.mockClear()
    vi.resetModules()
  })

  it("reports a missing locale file through the backend callback", async () => {
    const { dynamicBackend } = await import("@/i18n/config")
    dynamicBackend.init?.({} as never, {} as never, {} as never)

    const result = await readBackend(dynamicBackend, "missing", "namespace")

    expect(result.error?.message).toBe("Missing locale file for missing/namespace")
    expect(result.resource).toBeNull()
    expect(mocks.init).toHaveBeenCalledOnce()
    expect(mocks.plugins[0]).toBe(dynamicBackend as BackendModule)
  })

  it("loads every declared locale resource", async () => {
    const { dynamicBackend, localeLoaders, namespaces, supportedLngs } =
      await import("@/i18n/config")

    for (const language of supportedLngs) {
      for (const namespace of namespaces) {
        const result = await readBackend(dynamicBackend, language, namespace)
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
    const loaded = await readBackend(dynamicBackend, "en", "common")
    if (loaded.error) throw loaded.error
    expect(loaded.resource).toEqual({ synthetic: "resource" })

    const failure = new Error("loader failed")
    localeLoaders[key] = () => Promise.reject(failure)
    const received = await readBackend(dynamicBackend, "en", "common")
    expect(received.error).toBe(failure)
    localeLoaders[key] = original
  })
})
