import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

import { NewsDetailHero } from "@/components/news/NewsDetailHero"

const baseProps = {
  imageUrl: "https://picsum.photos/seed/news-detail/1200/675",
  displayTitle: "University Announces New AI Research Center",
}

describe("NewsDetailHero", () => {
  it("renders the hero image and a zoom button", () => {
    render(<NewsDetailHero {...baseProps} />)
    expect(screen.getByRole("button", { name: "news:actions.zoomImage" })).toBeInTheDocument()
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("renders a fallback figcaption when there is no display title", () => {
    render(<NewsDetailHero {...baseProps} displayTitle="" />)
    expect(screen.getByText("news:alt.heroFallback")).toBeInTheDocument()
  })

  it("opens and closes the lightbox", async () => {
    const user = userEvent.setup()
    render(<NewsDetailHero {...baseProps} />)
    await user.click(screen.getByRole("button", { name: "news:actions.zoomImage" }))
    const dialog = screen.getByRole("dialog")
    expect(dialog).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "common:buttons.close" }))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })
})
