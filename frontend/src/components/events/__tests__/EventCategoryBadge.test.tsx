import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

import { EventCategoryBadge } from "@/components/events/EventCategoryBadge"

function badgeElement(): HTMLElement {
  const badge = document.querySelector<HTMLElement>("span.events-badge-matte")
  if (!badge) throw new Error("Expected an event category badge")
  return badge
}

describe("EventCategoryBadge", () => {
  it("uses the compact style when size is omitted", () => {
    render(<EventCategoryBadge category="conference" />)

    expect(screen.getByText("events:categories.conference")).toBeInTheDocument()
    const badge = badgeElement()
    expect(badge).toHaveClass("px-2.5", "py-0.5", "text-[10px]")
    expect(badge).toHaveStyle({ "--_badge-accent": "var(--cat-amber-text)" })
  })

  it("uses the spacious style for the medium size", () => {
    render(<EventCategoryBadge category="workshop" size="md" />)

    expect(screen.getByText("events:categories.workshop")).toBeInTheDocument()
    expect(badgeElement()).toHaveClass("px-3", "py-1", "text-xs")
  })
})
