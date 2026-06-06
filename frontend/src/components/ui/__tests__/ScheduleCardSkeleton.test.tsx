import { describe, expect, it } from "vitest"
import { screen } from "@testing-library/react"

import { ScheduleCardSkeleton } from "@/components/ui/ScheduleCardSkeleton"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

// Each lesson placeholder contains exactly one Skeleton with the hardcoded
// ariaLabel "Loading subject", so the count is a reliable item-count probe.

describe("ScheduleCardSkeleton", () => {
  it("renders the default 3 lesson placeholders + an aria-busy container", async () => {
    const { container } = await renderWithRouter({
      ui: () => <ScheduleCardSkeleton />,
      authProvider: false,
    })
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull()
    expect(screen.getAllByLabelText("Loading subject")).toHaveLength(3)
  })

  it("respects a custom item count", async () => {
    await renderWithRouter({
      ui: () => <ScheduleCardSkeleton items={5} />,
      authProvider: false,
    })
    expect(screen.getAllByLabelText("Loading subject")).toHaveLength(5)
  })
})
