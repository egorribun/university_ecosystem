import { describe, expect, it } from "vitest"
import { render } from "@testing-library/react"

import { Spinner } from "@/components/ui/Spinner"

// Pure presentational — no providers needed; plain render.

describe("Spinner", () => {
  it.each([
    ["sm", "h-4"],
    ["md", "h-5"],
    ["lg", "h-8"],
  ] as const)("renders the %s size", (size, cls) => {
    const { container } = render(<Spinner size={size} />)
    const span = container.querySelector('span[aria-hidden="true"]')
    expect(span).not.toBeNull()
    expect(span?.className).toContain(cls)
  })

  it("defaults to md and forwards a custom className", () => {
    const { container } = render(<Spinner className="extra" />)
    const span = container.querySelector("span")
    expect(span?.className).toContain("h-5")
    expect(span?.className).toContain("extra")
  })
})
