import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { NewsCardBackground } from "@/components/dashboard/NewsCardBackground"

describe("NewsCardBackground", () => {
  it("renders one static category wash without blur or perpetual animation", () => {
    const { container } = render(<NewsCardBackground />)

    const background = container.querySelector("[aria-hidden='true']")
    expect(container.querySelectorAll("[aria-hidden='true']")).toHaveLength(1)
    expect(background).toHaveClass(
      "pointer-events-none",
      "absolute",
      "inset-0",
      "z-hide",
      "opacity-soft"
    )
    expect(background).toHaveAttribute(
      "style",
      expect.stringContaining(
        "background: linear-gradient(135deg, color-mix(in srgb, var(--dash-card-news-radial) 22%, transparent), transparent 72%)"
      )
    )
    expect(container.querySelector('[style*="animation"]')).toBeNull()
    expect(container.querySelector('[class*="blur"]')).toBeNull()
  })
})
