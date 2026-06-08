import { describe, expect, it } from "vitest"
import { screen } from "@testing-library/react"

import { ProfileCardSkeleton } from "@/components/ui/ProfileCardSkeleton"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

describe("ProfileCardSkeleton", () => {
  it("renders the cover placeholder by default", async () => {
    const { container } = await renderWithRouter({
      ui: () => <ProfileCardSkeleton />,
      authProvider: false,
    })
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull()
    expect(container.querySelector(".animate-skeleton-wave")).not.toBeNull()
    expect(screen.getByLabelText("Loading avatar")).toBeInTheDocument()
  })

  it("omits the cover when showCover is false", async () => {
    const { container } = await renderWithRouter({
      ui: () => <ProfileCardSkeleton showCover={false} />,
      authProvider: false,
    })
    expect(container.querySelector(".animate-skeleton-wave")).toBeNull()
    // Avatar + stats still render in the no-cover branch.
    expect(screen.getByLabelText("Loading avatar")).toBeInTheDocument()
  })
})
