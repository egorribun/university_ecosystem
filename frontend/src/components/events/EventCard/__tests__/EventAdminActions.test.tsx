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

import { EventAdminActions } from "@/components/events/EventCard/EventAdminActions"

const baseProps = {
  menuAnchor: null,
  setMenuAnchor: vi.fn(),
  onEdit: vi.fn(),
  onDelete: vi.fn(),
  menuId: "evt-admin-menu",
}

describe("EventAdminActions", () => {
  it("renders a collapsed actions trigger when no anchor is set", () => {
    render(<EventAdminActions {...baseProps} />)
    const trigger = screen.getByRole("button", { name: "events:card.aria.actions" })
    expect(trigger).toHaveAttribute("aria-expanded", "false")
    expect(screen.queryByRole("button", { name: "common:buttons.edit" })).not.toBeInTheDocument()
  })

  it("opens the menu by setting the anchor when the trigger is clicked", async () => {
    const user = userEvent.setup()
    const setMenuAnchor = vi.fn()
    render(<EventAdminActions {...baseProps} setMenuAnchor={setMenuAnchor} />)
    await user.click(screen.getByRole("button", { name: "events:card.aria.actions" }))
    expect(setMenuAnchor).toHaveBeenCalledOnce()
  })

  it("shows edit/delete and fires their callbacks when the menu is open", async () => {
    const user = userEvent.setup()
    const onEdit = vi.fn()
    const onDelete = vi.fn()
    const anchor = document.createElement("button")
    render(
      <EventAdminActions {...baseProps} menuAnchor={anchor} onEdit={onEdit} onDelete={onDelete} />
    )
    await user.click(screen.getByRole("button", { name: "common:buttons.edit" }))
    expect(onEdit).toHaveBeenCalledOnce()
    await user.click(screen.getByRole("button", { name: "common:buttons.delete" }))
    expect(onDelete).toHaveBeenCalledOnce()
  })
})
