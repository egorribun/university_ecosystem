import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const joseMocks = vi.hoisted(() => ({
  createRemoteJWKSet: vi.fn(),
  jwtVerify: vi.fn(),
}))

vi.mock("jose", () => joseMocks)

describe("ssrAuth real JWKS path", () => {
  beforeEach(() => {
    joseMocks.createRemoteJWKSet.mockReset()
    joseMocks.jwtVerify.mockReset()
    joseMocks.createRemoteJWKSet.mockImplementation((url: URL) => ({ url }))
    joseMocks.jwtVerify.mockResolvedValue({
      payload: { sub: "real-jwks-user", role: "teacher" },
    })
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it("prefers the runtime backend origin for a reusable SSR image", async () => {
    vi.resetModules()
    vi.stubGlobal("window", undefined)
    vi.stubEnv("VITE_BACKEND_ORIGIN", "https://build-time.example")
    vi.stubEnv("BACKEND_ORIGIN", "http://release-backend:8000/")
    const { validateJwt } = await import("../ssrAuth")

    await expect(validateJwt("runtime-token")).resolves.toMatchObject({
      isAuth: true,
    })
    expect(joseMocks.createRemoteJWKSet).toHaveBeenCalledWith(
      new URL("http://release-backend:8000/.well-known/jwks.json")
    )
  })

  it("uses the configured backend origin for the real verification path", async () => {
    vi.resetModules()
    vi.stubEnv("VITE_BACKEND_ORIGIN", "https://api.example.test")
    const { validateJwt } = await import("../ssrAuth")

    await expect(validateJwt("signed-token")).resolves.toEqual({
      isAuth: true,
      user: { role: "teacher" },
      loading: false,
    })
    expect(joseMocks.createRemoteJWKSet).toHaveBeenCalledWith(
      new URL("https://api.example.test/.well-known/jwks.json")
    )
    expect(joseMocks.jwtVerify).toHaveBeenCalledWith(
      "signed-token",
      { url: new URL("https://api.example.test/.well-known/jwks.json") },
      { audience: "university-ecosystem-api" }
    )

    await expect(validateJwt("second-token")).resolves.toMatchObject({ isAuth: true })
    expect(joseMocks.createRemoteJWKSet).toHaveBeenCalledOnce()
  })

  it("falls back to the local backend origin when no origin is configured", async () => {
    vi.resetModules()
    vi.stubEnv("VITE_BACKEND_ORIGIN", "")
    const { validateJwt } = await import("../ssrAuth")

    await expect(validateJwt("local-token")).resolves.toMatchObject({
      isAuth: true,
      user: { role: "teacher" },
    })
    expect(joseMocks.createRemoteJWKSet).toHaveBeenCalledWith(
      new URL("http://localhost:8000/.well-known/jwks.json")
    )
  })
})
