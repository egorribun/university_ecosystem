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

import { EventDetailHero } from "@/components/events/EventDetailHero"

const baseProps = { imageUrl: "https://picsum.photos/seed/event-detail/1200/675" }

describe("EventDetailHero", () => {
  it("renders the hero image and a zoom button", () => {
    render(<EventDetailHero {...baseProps} />)
    expect(screen.getByRole("button", { name: "events:detail.actions.zoom" })).toBeInTheDocument()
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("opens and closes the lightbox", async () => {
    const user = userEvent.setup()
    render(<EventDetailHero {...baseProps} />)
    await user.click(screen.getByRole("button", { name: "events:detail.actions.zoom" }))
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "common:buttons.close" }))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })
})
