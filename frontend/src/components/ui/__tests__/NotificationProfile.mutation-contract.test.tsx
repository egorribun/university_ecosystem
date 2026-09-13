import { cleanup, screen } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"

import { NotificationRelevanceScore } from "@/components/ui/NotificationRelevanceScore"
import { ProfileCardSkeleton } from "@/components/ui/ProfileCardSkeleton"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

afterEach(cleanup)

describe("NotificationRelevanceScore mutation contracts", () => {
  it.each([
    ["high", "bg-brand", [true, false, false]],
    ["medium", "bg-warning-text", [true, true, false]],
    ["low", "bg-(--text-tertiary)", [true, true, true]],
  ] as const)("keeps dot geometry and progression for %s", async (relevance, active, states) => {
    const { container } = await renderWithRouter({
      ui: () => <NotificationRelevanceScore relevance={relevance} />,
      authProvider: false,
    })
    const dots = Array.from(container.querySelectorAll<HTMLElement>('span[aria-hidden="true"]'))
    expect(dots).toHaveLength(3)
    expect(dots.every((dot) => dot.classList.contains("block"))).toBe(true)
    expect(dots.every((dot) => dot.classList.contains("h-1.5"))).toBe(true)
    expect(dots.every((dot) => dot.classList.contains("w-1.5"))).toBe(true)
    expect(dots.every((dot) => dot.classList.contains("rounded-full"))).toBe(true)
    expect(dots.every((dot) => dot.classList.contains("transition-colors"))).toBe(true)
    expect(dots.map((dot) => dot.classList.contains(active))).toEqual(states)
  })
})

describe("ProfileCardSkeleton mutation contracts", () => {
  it("uses an empty default className and keeps the cover overlap geometry", async () => {
    const { container } = await renderWithRouter({
      ui: () => <ProfileCardSkeleton />,
      authProvider: false,
    })
    const card = await screen.findByLabelText("Loading profile")
    expect(card.className).toBe(
      "rounded-2xl border border-white/(--opacity-subtle) bg-input-mix overflow-hidden "
    )
    expect(card.className).not.toContain("Stryker was here")
    const avatarOffset = container.querySelector(".relative > div.mb-4")
    expect(avatarOffset).toHaveClass("-mt-12", "mb-4", "sm:-mt-16")
  })
})
