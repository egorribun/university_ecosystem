import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { DashboardBackdrop } from "@/components/dashboard/DashboardBackdrop"

describe("DashboardBackdrop", () => {
  it("uses a static editorial wash without blur or perpetual animation", () => {
    const { container } = render(
      <DashboardBackdrop isNarrow={false} prefersReducedMotion={false} />
    )

    expect(container.querySelector('[style*="animation"]')).toBeNull()
    expect(container.querySelector('[style*="filter"]')).toBeNull()
    expect(container.querySelectorAll("[aria-hidden='true'] > div")).toHaveLength(1)
  })
})
