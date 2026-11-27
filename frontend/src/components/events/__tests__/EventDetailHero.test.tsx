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
import { expectBaseUtility } from "@/tests/helpers/expectBaseUtility"

const baseProps = { imageUrl: "https://picsum.photos/seed/event-detail/1200/675" }

describe("EventDetailHero", () => {
  it("renders the hero image and a zoom button", () => {
    render(<EventDetailHero {...baseProps} />)
    const zoom = screen.getByRole("button", { name: "events:detail.actions.zoom" })
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    // The scrim is black in both themes, so the icon stays white.
    expectBaseUtility(zoom, "width", "calc(var(--spacing) * 11)")
    expectBaseUtility(zoom, "color", "var(--color-white)")
  })

  it("opens and closes the lightbox", async () => {
    const user = userEvent.setup()
    render(<EventDetailHero {...baseProps} />)
    await user.click(screen.getByRole("button", { name: "events:detail.actions.zoom" }))
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    const close = screen.getByRole("button", { name: "common:buttons.close" })
    expectBaseUtility(close, "width", "calc(var(--spacing) * 11)")
    expectBaseUtility(close, "height", "calc(var(--spacing) * 11)")
    await user.click(close)
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })
})
