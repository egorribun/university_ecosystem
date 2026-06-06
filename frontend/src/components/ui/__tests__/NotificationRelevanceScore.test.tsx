import { describe, expect, it } from "vitest"

import { NotificationRelevanceScore } from "@/components/ui/NotificationRelevanceScore"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

// Prop-driven indicator. Mounted via renderWithRouter for the LanguageProvider
// (useTranslation); authProvider:false skips the /users/me round-trip. Assertions
// target the structural a11y surface so they're i18n-namespace independent.

describe("NotificationRelevanceScore", () => {
  it.each(["high", "medium", "low"] as const)(
    "renders 3 indicator dots + an aria-label for relevance=%s",
    async (relevance) => {
      const { container } = await renderWithRouter({
        ui: () => <NotificationRelevanceScore relevance={relevance} />,
        authProvider: false,
      })
      expect(container.querySelectorAll('span[aria-hidden="true"]')).toHaveLength(3)
      const wrapper = container.querySelector("div[aria-label]")
      expect(wrapper).not.toBeNull()
      expect(wrapper?.getAttribute("aria-label")).toBeTruthy()
    }
  )

  it("forwards a custom className to the wrapper", async () => {
    const { container } = await renderWithRouter({
      ui: () => <NotificationRelevanceScore relevance="high" className="my-cls" />,
      authProvider: false,
    })
    expect(container.querySelector("div.my-cls")).not.toBeNull()
  })
})
