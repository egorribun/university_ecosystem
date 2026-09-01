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

  test("uses a caller-provided label for both the hidden heading and status content", async () => {
    const { container } = await renderWithA11y(<LoadingState label="Loading profile" />)

    expect(screen.getByRole("heading", { name: "Loading profile" })).toHaveClass("sr-only")
    expect(screen.getByRole("status")).toHaveTextContent("Loading profile")
    expect(screen.getByRole("status")).toHaveClass(
      "flex",
      "flex-col",
      "items-center",
      "justify-center",
      "min-h-60dvh",
      "text-center"
    )
    expect(container.querySelector(".animate-spin")).toHaveClass(
      "h-12",
      "w-12",
      "rounded-full",
      "border-4",
      "border-t-brand"
    )
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument()
  })
})
