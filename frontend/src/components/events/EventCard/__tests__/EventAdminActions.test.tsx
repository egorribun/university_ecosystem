import { createEvent, fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useState } from "react"
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

function ControlledEventAdminActions({ disabled = false }: { disabled?: boolean }) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null)
  return (
    <EventAdminActions
      {...baseProps}
      disabled={disabled}
      menuAnchor={anchor}
      setMenuAnchor={setAnchor}
    />
  )
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
    expect(trigger).toHaveClass("min-h-11", "min-w-11")
    expect(trigger).not.toHaveClass("min-h-0!")
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

  it("toggles the controlled menu and exposes an accessible trigger relationship", async () => {
    const user = userEvent.setup()
    render(<ControlledEventAdminActions />)
    const trigger = screen.getByRole("button", { name: "events:card.aria.actions" })

    expect(trigger).toHaveAttribute("id", "evt-admin-menu-button")
    expect(trigger).toHaveAttribute("aria-haspopup", "menu")
    await user.click(trigger)
    const menu = screen.getByRole("menu")
    expect(menu).toHaveAttribute("aria-labelledby", "evt-admin-menu-button")
    expect(screen.getByRole("menuitem", { name: "common:buttons.edit" })).toHaveFocus()

    await user.click(trigger)
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it("supports cyclic arrow navigation, Escape focus return, and disabled state", async () => {
    const user = userEvent.setup()
    const { rerender } = render(<ControlledEventAdminActions />)
    const trigger = screen.getByRole("button", { name: "events:card.aria.actions" })
    await user.click(trigger)
    const edit = screen.getByRole("menuitem", { name: "common:buttons.edit" })
    const remove = screen.getByRole("menuitem", { name: "common:buttons.delete" })

    expect(edit).toHaveFocus()
    await user.keyboard("{ArrowDown}")
    expect(remove).toHaveFocus()
    await user.keyboard("{ArrowDown}")
    expect(edit).toHaveFocus()
    await user.keyboard("{ArrowUp}")
    expect(remove).toHaveFocus()
    await user.keyboard("{Escape}")
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()

    rerender(<ControlledEventAdminActions disabled />)
    expect(trigger).toBeDisabled()
    await user.click(trigger)
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
  })

  it("closes an open controlled menu when the action becomes disabled", async () => {
    const user = userEvent.setup()
    const { rerender } = render(<ControlledEventAdminActions />)
    const trigger = screen.getByRole("button", { name: "events:card.aria.actions" })

    await user.click(trigger)
    expect(screen.getByRole("menu")).toBeInTheDocument()

    rerender(<ControlledEventAdminActions disabled />)

    expect(trigger).toBeDisabled()
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument())

    rerender(<ControlledEventAdminActions />)
    expect(trigger).toBeEnabled()
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument())
  })

  it("suppresses callbacks and stale controlled menu items while disabled", () => {
    const onEdit = vi.fn()
    const onDelete = vi.fn()
    const setMenuAnchor = vi.fn()
    const anchor = document.createElement("button")

    render(
      <EventAdminActions
        {...baseProps}
        disabled
        menuAnchor={anchor}
        setMenuAnchor={setMenuAnchor}
        onEdit={onEdit}
        onDelete={onDelete}
      />
    )

    const trigger = screen.getByRole("button", { name: "events:card.aria.actions" })
    expect(trigger).toBeDisabled()
    expect(trigger).toHaveAttribute("aria-expanded", "false")
    expect(trigger).not.toHaveAttribute("aria-controls")
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
    expect(screen.queryByRole("menuitem")).not.toBeInTheDocument()
    fireEvent.click(trigger)
    expect(onEdit).not.toHaveBeenCalled()
    expect(onDelete).not.toHaveBeenCalled()
  })

  it("dismisses an open controlled menu on an outside pointer interaction", async () => {
    const user = userEvent.setup()
    render(
      <>
        <ControlledEventAdminActions />
        <button type="button">Outside</button>
      </>
    )

    await user.click(screen.getByRole("button", { name: "events:card.aria.actions" }))
    expect(screen.getByRole("menu")).toBeInTheDocument()
    const outside = screen.getByRole("button", { name: "Outside" })
    await user.click(outside)

    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
    expect(outside).toHaveFocus()
  })

  it("ignores malformed outside-pointer targets without dismissing the menu", async () => {
    const user = userEvent.setup()
    const addEventListener = vi.spyOn(document, "addEventListener")
    render(<ControlledEventAdminActions />)

    await user.click(screen.getByRole("button", { name: "events:card.aria.actions" }))
    const listener = addEventListener.mock.calls.find(([type]) => type === "mousedown")?.[1]
    expect(listener).toBeTypeOf("function")

    ;(listener as EventListener)({ target: null } as unknown as Event)
    expect(screen.getByRole("menu")).toBeInTheDocument()
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
    const menu = screen.getByRole("menu")
    expect(menu).toHaveAttribute("id", "evt-admin-menu")
    const edit = screen.getByRole("menuitem", { name: "common:buttons.edit" })
    const remove = screen.getByRole("menuitem", { name: "common:buttons.delete" })
    expect(edit).toHaveClass("min-h-11")
    expect(remove).toHaveClass("min-h-11")
    await user.click(edit)
    expect(onEdit).toHaveBeenCalledOnce()
    expect(setMenuAnchor).toHaveBeenCalledWith(null)
    await user.click(remove)
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

    await user.click(screen.getByRole("menuitem", { name: "common:buttons.edit" }))
    expect(parentClick).not.toHaveBeenCalled()
  })

  it("stops menu keyboard events from bubbling into the event card", () => {
    const parentKeyDown = vi.fn()
    const anchor = document.createElement("button")
    render(
      <div role="button" tabIndex={0} onClick={() => undefined} onKeyDown={parentKeyDown}>
        <EventAdminActions {...baseProps} menuAnchor={anchor} />
      </div>
    )

    fireEvent.keyDown(screen.getByRole("menu"), { key: "ArrowDown" })
    expect(parentKeyDown).not.toHaveBeenCalled()
  })

  it("keeps non-navigation keys passive and tolerates a menu with no enabled items", () => {
    const anchor = document.createElement("button")
    render(<EventAdminActions {...baseProps} menuAnchor={anchor} />)
    const menu = screen.getByRole("menu")
    const edit = screen.getByRole("menuitem", { name: "common:buttons.edit" })
    edit.focus()

    const tabEvent = createEvent.keyDown(menu, { key: "Tab", cancelable: true })
    fireEvent(menu, tabEvent)
    expect(tabEvent.defaultPrevented).toBe(false)
    expect(edit).toHaveFocus()
    expect(screen.getByRole("menu")).toBeInTheDocument()

    menu.replaceChildren()
    fireEvent.keyDown(menu, { key: "ArrowDown" })
    expect(screen.getByRole("menu")).toBeInTheDocument()
  })
})
