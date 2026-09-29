import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

const translationState = vi.hoisted(() => ({ namespaces: [] as unknown[] }))

vi.mock("react-i18next", () => ({
  useTranslation: (namespaces: unknown) => {
    translationState.namespaces.push(namespaces)
    return {
      t: (key: string) => key,
      i18n: { language: "en", changeLanguage: () => Promise.resolve() },
    }
  },
}))

vi.mock("framer-motion", () => ({
  m: {
    div: ({
      whileHover,
      children,
      ...props
    }: {
      whileHover?: unknown
      children?: React.ReactNode
    }) => (
      <div {...props} data-while-hover={JSON.stringify(whileHover)}>
        {children}
      </div>
    ),
  },
}))

vi.mock("@/components/settings", () => ({
  SectionCard: ({ children, ...props }: { children?: React.ReactNode }) => (
    <section {...props}>{children}</section>
  ),
}))

import { AchievementsSection } from "@/components/profile/AchievementsSection"

describe("AchievementsSection mutation contracts", () => {
  beforeEach(() => {
    translationState.namespaces = []
  })

  it("omits the section for an empty collection", () => {
    const { container } = render(
      <AchievementsSection achievements={[]} onAchievementClick={vi.fn()} />
    )
    expect(container).toBeEmptyDOMElement()
  })

  it("keeps heading, card animation, issuer fallback, and click semantics exact", async () => {
    const user = userEvent.setup()
    const onAchievementClick = vi.fn()
    const first = { key: "first", name: "Dean's list", issuer: "Academic Board" }
    const second = { key: "second", name: "Research award", issuer: "" }
    render(
      <AchievementsSection achievements={[first, second]} onAchievementClick={onAchievementClick} />
    )

    expect(translationState.namespaces).toContainEqual(["profile"])
    expect(
      screen.getByRole("heading", { name: "profile:sections.achievements" })
    ).toBeInTheDocument()
    expect(screen.getAllByText("Academic Board")).toHaveLength(2)
    expect(screen.getByText("Research award")).toBeInTheDocument()

    const cards = screen
      .getAllByText(/Dean's list|Research award/)
      .map((node) => node.closest("div")?.parentElement)
    expect(cards[0]).toHaveAttribute("data-while-hover", JSON.stringify({ y: -2 }))
    expect(cards[0]).toHaveClass(
      "flex",
      "items-start",
      "gap-3",
      "p-4",
      "rounded-2xl",
      "transition-all",
      "cursor-pointer",
      "group"
    )

    await user.click(screen.getByText("Research award"))
    expect(onAchievementClick).toHaveBeenCalledWith(second)
  })
})
