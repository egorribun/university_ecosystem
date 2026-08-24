import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { AchievementsSection } from "@/components/profile/AchievementsSection"

describe("AchievementsSection", () => {
  it("uses the issuer fallback and reports the clicked achievement", async () => {
    const achievement = { key: "first", name: "Dean's list" }
    const onAchievementClick = vi.fn()
    render(
      <AchievementsSection achievements={[achievement]} onAchievementClick={onAchievementClick} />
    )

    expect(screen.getByText("Academic Board")).toBeInTheDocument()
    await userEvent.click(screen.getByText("Dean's list"))
    expect(onAchievementClick).toHaveBeenCalledWith(achievement)
  })
})
