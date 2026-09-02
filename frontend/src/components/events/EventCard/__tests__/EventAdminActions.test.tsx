import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi } from "vitest"

const { useTranslationMock, translateMock } = vi.hoisted(() => {
  const translateMock = vi.fn((key: string) => key)
  return {
    translateMock,
    useTranslationMock: vi.fn(() => ({
      t: translateMock,
      i18n: { language: "en", changeLanguage: () => Promise.resolve() },
    })),
  }
})

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: useTranslationMock,
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
  beforeEach(() => {
    useTranslationMock.mockClear()
    translateMock.mockClear()
  })

  it("renders a collapsed actions trigger when no anchor is set", () => {
    render(<EventAdminActions {...baseProps} />)
    const trigger = screen.getByRole("button", { name: "events:card.aria.actions" })
    expect(trigger).toHaveAttribute("aria-expanded", "false")
    expect(trigger).not.toHaveAttribute("aria-controls")
    expect(useTranslationMock).toHaveBeenCalledWith(["events", "common"])
    expect(translateMock).toHaveBeenCalledWith("events:card.aria.actions")
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
    const setMenuAnchor = vi.fn()
    render(
      <EventAdminActions
        {...baseProps}
        menuAnchor={anchor}
        setMenuAnchor={setMenuAnchor}
        onEdit={onEdit}
        onDelete={onDelete}
      />
    )
    const trigger = screen.getByRole("button", { name: "events:card.aria.actions" })
    expect(trigger).toHaveAttribute("aria-controls", "evt-admin-menu")
    expect(trigger).toHaveAttribute("aria-expanded", "true")
    await user.click(screen.getByRole("button", { name: "common:buttons.edit" }))
    expect(onEdit).toHaveBeenCalledOnce()
    expect(setMenuAnchor).toHaveBeenCalledWith(null)
    await user.click(screen.getByRole("button", { name: "common:buttons.delete" }))
    expect(onDelete).toHaveBeenCalledOnce()
    expect(setMenuAnchor).toHaveBeenCalledWith(null)
  })

  it("stops menu clicks from bubbling into the event card", async () => {
    const user = userEvent.setup()
    const parentClick = vi.fn()
    const anchor = document.createElement("button")
    render(
      <div
        data-testid="event-parent"
        role="button"
        tabIndex={0}
        onClick={parentClick}
        onKeyDown={() => {}}
      >
        <EventAdminActions {...baseProps} menuAnchor={anchor} />
      </div>
    )

    await user.click(screen.getByRole("button", { name: "common:buttons.edit" }))
    expect(parentClick).not.toHaveBeenCalled()
  })
})
