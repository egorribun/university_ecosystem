import { render } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

afterEach(() => {
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})

describe("ParticleAuthBackground closure", () => {
  it("renders the lightweight layout fallback in E2E mode", async () => {
    vi.resetModules()
    vi.stubEnv("VITE_E2E_MODE", "true")
    const { default: ParticleAuthBackground } = await import("../ParticleAuthBackground")
    const { container } = render(<ParticleAuthBackground />)

    expect(container.querySelector("canvas")).not.toBeInTheDocument()
    expect(container.firstElementChild).toHaveAttribute("aria-hidden", "true")
    expect(container.firstElementChild?.querySelector(".bg-linear-to-b")).toBeInTheDocument()
  })

  it("stops safely when the canvas context is unavailable", async () => {
    vi.resetModules()
    vi.stubEnv("VITE_E2E_MODE", "")
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null)
    const { default: ParticleAuthBackground } = await import("../ParticleAuthBackground")
    const { container } = render(<ParticleAuthBackground />)

    expect(container.querySelector("canvas")).toBeInTheDocument()
  })
})
