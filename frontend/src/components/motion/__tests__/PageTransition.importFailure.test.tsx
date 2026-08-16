import { render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

vi.mock("framer-motion", () => {
  throw new Error("motion chunk unavailable")
})

describe("PageTransition lazy-module failure", () => {
  afterEach(() => {
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
})
