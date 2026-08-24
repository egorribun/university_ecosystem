import { afterEach, describe, expect, it, vi } from "vitest"

import { resolveSsrBackendOrigin } from "@/api/backendOrigin"

afterEach(() => {
  vi.unstubAllGlobals()
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
})
