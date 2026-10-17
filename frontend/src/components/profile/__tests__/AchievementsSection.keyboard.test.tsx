import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { AchievementsSection } from "@/components/profile/AchievementsSection"

describe("AchievementsSection keyboard access", () => {
  it("keeps each achievement heading navigable and activates its native action once", async () => {
    const user = userEvent.setup()
    const achievement = { key: "first", name: "Dean's list" }
    const onAchievementClick = vi.fn()
    render(
      <AchievementsSection achievements={[achievement]} onAchievementClick={onAchievementClick} />
    )

    const heading = screen.getByRole("heading", { level: 3, name: "Dean's list" })
    const button = within(heading).getByRole("button", { name: "Dean's list" })
    expect(button.tagName).toBe("BUTTON")
    expect(button).toHaveClass("focus-visible:ring-2", "min-h-11", "min-w-11")

    await user.tab()
    expect(button).toHaveFocus()

    await user.keyboard("{Enter}")
    expect(onAchievementClick).toHaveBeenCalledTimes(1)
    expect(onAchievementClick).toHaveBeenCalledWith(achievement)

    onAchievementClick.mockClear()
    await user.keyboard(" ")
    expect(onAchievementClick).toHaveBeenCalledTimes(1)
    expect(onAchievementClick).toHaveBeenCalledWith(achievement)

    onAchievementClick.mockClear()
    await user.click(button)
    expect(onAchievementClick).toHaveBeenCalledTimes(1)
    expect(onAchievementClick).toHaveBeenCalledWith(achievement)
  })

  it("keeps card-body pointer activation working", async () => {
    const user = userEvent.setup()
    const achievement = {
      key: "community",
      name: "Community Research",
      issuer: "Northbridge University",
    }
    const onAchievementClick = vi.fn()
    render(
      <AchievementsSection achievements={[achievement]} onAchievementClick={onAchievementClick} />
    )

    await user.click(screen.getByText("Northbridge University"))

    expect(onAchievementClick).toHaveBeenCalledTimes(1)
    expect(onAchievementClick).toHaveBeenCalledWith(achievement)
  })
})
