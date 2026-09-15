import { afterEach, describe, expect, it, vi } from "vitest"

import { resolveSsrBackendOrigin } from "@/api/backendOrigin"

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

describe("resolveSsrBackendOrigin", () => {
  it("uses and normalizes the runtime origin during SSR", () => {
    vi.stubGlobal("window", undefined)
    vi.stubGlobal("process", {
      env: { BACKEND_ORIGIN: "  https://backend.internal///  " },
    })

    expect(resolveSsrBackendOrigin()).toBe("https://backend.internal")
  })

  it("ignores the server runtime origin in a browser", () => {
    vi.stubGlobal("process", {
      env: { BACKEND_ORIGIN: "https://backend.internal" },
    })

    expect(resolveSsrBackendOrigin()).toBe("http://localhost:8000")
  })

  it.each([
    {
      name: "falls back to the build origin when runtime origin is blank",
      windowValue: undefined,
      processValue: { env: { BACKEND_ORIGIN: "   " } },
      viteValue: "  https://build.internal///  ",
      expected: "https://build.internal",
    },
    {
      name: "falls back to the default when both configured origins are blank",
      windowValue: undefined,
      processValue: { env: { BACKEND_ORIGIN: "" } },
      viteValue: "   ",
      expected: "http://localhost:8000",
    },
    {
      name: "keeps every trailing slash normalized",
      windowValue: undefined,
      processValue: { env: { BACKEND_ORIGIN: "https://runtime.internal////" } },
      viteValue: "https://build.internal",
      expected: "https://runtime.internal",
    },
  ])("$name", ({ windowValue, processValue, viteValue, expected }) => {
    vi.resetModules()
    vi.stubGlobal("window", windowValue)
    vi.stubGlobal("process", processValue)
    vi.stubEnv("VITE_BACKEND_ORIGIN", viteValue)

    expect(resolveSsrBackendOrigin()).toBe(expected)
  })

  it("does not throw when the runtime origin is missing", () => {
    vi.stubGlobal("window", undefined)
    vi.stubEnv("VITE_BACKEND_ORIGIN", "")
    vi.stubGlobal("process", { env: { BACKEND_ORIGIN: undefined } })

    expect(resolveSsrBackendOrigin()).toBe("http://localhost:8000")
  })
})
