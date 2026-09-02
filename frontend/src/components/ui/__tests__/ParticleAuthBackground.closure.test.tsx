import { render } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  document.documentElement.style.removeProperty("--primary-main")
  document.documentElement.style.removeProperty("--primary-hover")
})

describe("ParticleAuthBackground performance contract", () => {
  it.each(["", "true"])(
    "renders the same static, non-animated backdrop when VITE_E2E_MODE=%j",
    async (e2eMode) => {
      vi.resetModules()
      vi.stubEnv("VITE_E2E_MODE", e2eMode)
      const requestFrame = vi.spyOn(window, "requestAnimationFrame")
      const { default: ParticleAuthBackground } = await import("../ParticleAuthBackground")
      const { container } = render(<ParticleAuthBackground />)

      expect(container.querySelector("canvas")).not.toBeInTheDocument()
      expect(container.firstElementChild).toHaveAttribute("aria-hidden", "true")
      expect(container.firstElementChild?.querySelector(".bg-linear-to-b")).toBeInTheDocument()
      expect(requestFrame).not.toHaveBeenCalled()
    }
  )
})
