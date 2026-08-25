import { screen } from "@testing-library/react"
import LoadingState from "@/components/feedback/LoadingState"
import { renderWithA11y } from "@/tests/axeTest"
import { describe, expect, test } from "vitest"

describe("LoadingState", () => {
  test("renders an accessible busy status with page landmarks", async () => {
    const { container } = await renderWithA11y(<LoadingState />)

    const status = screen.getByRole("status")
    expect(status).toHaveAttribute("aria-busy", "true")
    expect(status).toHaveAttribute("aria-live", "polite")
    expect(screen.getAllByText(/loading/i)[0]).toBeInTheDocument()
    // Wave 120 SW3 (a11y): Layout.tsx switched from `<main id="main">` to
    // `<div data-scroll-root>` to fix duplicate main landmark — MainLayout
    // already provides the page-level main. Test now checks the data
    // attribute that stayed on the wrapper.
    expect(container.querySelector("[data-scroll-root]")).not.toBeNull()
    expect(container.querySelector("header")).not.toBeNull()
  })
})
