import { render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

vi.mock("framer-motion", () => {
  throw new Error("motion chunk unavailable")
})

describe("PageTransition lazy-module failure", () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.restoreAllMocks()
  })

  it("keeps children visible and reports a failed motion import in development", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined)
    const { default: PageTransition } = await import("@/components/motion/PageTransition")

    render(
      <PageTransition>
        <div>Fallback child</div>
      </PageTransition>
    )

    expect(screen.getByText("Fallback child")).toBeInTheDocument()
    await waitFor(() => expect(warn).toHaveBeenCalledOnce())
    const [message, error] = warn.mock.calls[0]!
    expect(message).toBe("[PageTransition] framer-motion load failed:")
    expect(error).toBeInstanceOf(Error)
    expect((error as Error & { cause?: Error }).cause).toEqual(
      expect.objectContaining({ message: "motion chunk unavailable" })
    )
  })

  it("keeps children visible without logging a failed import in production", async () => {
    vi.stubEnv("DEV", false)
    vi.spyOn(window, "matchMedia").mockReturnValue({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as unknown as MediaQueryList)
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined)
    const { default: PageTransition } = await import("@/components/motion/PageTransition")

    render(
      <PageTransition>
        <div>Production fallback child</div>
      </PageTransition>
    )

    expect(screen.getByText("Production fallback child")).toBeInTheDocument()
    await waitFor(() => expect(warn).not.toHaveBeenCalled())
  })
})
