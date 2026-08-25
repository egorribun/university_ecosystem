import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { Skeleton } from "@/components/ui/Skeleton"

describe("Skeleton", () => {
  it("is a busy decorative placeholder by default without creating a live region", () => {
    const { container } = render(<Skeleton />)
    const skeleton = container.firstElementChild

    expect(skeleton).toHaveAttribute("aria-busy", "true")
    expect(skeleton).toHaveAttribute("aria-hidden", "true")
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
  })

  it("exposes one labelled polite status when an aria label is supplied", () => {
    render(<Skeleton ariaLabel="Loading profile" aria-busy="false" />)
    const status = screen.getByRole("status", { name: "Loading profile" })

    expect(status).toHaveAttribute("aria-busy", "true")
    expect(status).toHaveAttribute("aria-live", "polite")
    expect(status).not.toHaveAttribute("aria-hidden")
  })
})
