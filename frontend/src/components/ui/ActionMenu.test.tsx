import { describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { axe } from "jest-axe"

import { ActionMenu, type ActionMenuItem } from "./ActionMenu"

/**
 * ActionMenu ARIA + keyboard-nav + interaction tests.
 *
 * Coverage:
 *  - trigger has aria-label / aria-haspopup="menu" / aria-expanded;
 *  - menu opens on click and exposes role="menu" + role="menuitem";
 *  - keyboard nav: Escape closes, ArrowDown focuses first item,
 *    ArrowDown / ArrowUp cycle through items;
 *  - item clicks dispatch onClick + close menu;
 *  - disabled items don't dispatch and skip in arrow nav;
 *  - axe: zero violations open + closed.
 */

const items: ActionMenuItem[] = [
  { label: "Edit", onClick: vi.fn() },
  { label: "Archive", onClick: vi.fn() },
  { label: "Delete", onClick: vi.fn(), variant: "danger" },
]

describe("ActionMenu — trigger", () => {
  it("renders the trigger with the documented ARIA shape", () => {
    render(<ActionMenu items={items} />)
    const trigger = screen.getByRole("button", { name: /open menu/i })
    expect(trigger).toHaveAttribute("aria-haspopup", "menu")
    expect(trigger).toHaveAttribute("aria-expanded", "false")
  })

  it("uses a custom aria-label when supplied", () => {
    render(<ActionMenu items={items} ariaLabel="More actions" />)
    expect(screen.getByRole("button", { name: /more actions/i })).toBeInTheDocument()
  })
})

describe("ActionMenu — open + close", () => {
  it("opens the menu on click and exposes role='menu'", async () => {
    const user = userEvent.setup()
    render(<ActionMenu items={items} />)
    await user.click(screen.getByRole("button", { name: /open menu/i }))

    expect(screen.getByRole("menu")).toBeInTheDocument()
    expect(screen.getAllByRole("menuitem")).toHaveLength(items.length)
    expect(screen.getByRole("button", { name: /open menu/i })).toHaveAttribute(
      "aria-expanded",
      "true"
    )
  })

  it("closes on Escape", async () => {
    const user = userEvent.setup()
    render(<ActionMenu items={items} />)
    await user.click(screen.getByRole("button", { name: /open menu/i }))
    expect(screen.getByRole("menu")).toBeInTheDocument()

    await user.keyboard("{Escape}")
    expect(screen.queryByRole("menu")).toBeNull()
  })

  it("supports arrow navigation, custom trigger content, and click-outside dismissal", async () => {
    const user = userEvent.setup()
    render(
      <ActionMenu
        placement="bottom-start"
        menuClassName="custom-menu"
        triggerClassName="custom-trigger"
        trigger={<span>Custom trigger</span>}
        items={[
          { label: "Edit", onClick: vi.fn(), icon: <span data-testid="edit-icon" /> },
          { label: "Disabled", onClick: vi.fn(), disabled: true },
          { label: "Delete", onClick: vi.fn(), variant: "danger", ariaLabel: "Remove item" },
        ]}
      />
    )

    const trigger = screen.getByRole("button", { name: /open menu/i })
    expect(screen.getByText("Custom trigger")).toBeInTheDocument()
    await user.click(trigger)
    expect(screen.getByRole("menu")).toHaveClass("left-0", "custom-menu")
    expect(screen.getByTestId("edit-icon")).toBeInTheDocument()

    fireEvent.keyDown(trigger, { key: "ArrowDown" })
    const edit = screen.getByRole("menuitem", { name: "Edit" })
    expect(document.activeElement).toBe(edit)
    const remove = screen.getByRole("menuitem", { name: "Remove item" })
    const removeFocus = vi.spyOn(remove, "focus")
    fireEvent.keyDown(edit, { key: "ArrowDown" })
    expect(removeFocus).toHaveBeenCalledOnce()
    const editFocus = vi.spyOn(edit, "focus")
    fireEvent.keyDown(remove, { key: "ArrowUp" })
    expect(editFocus).toHaveBeenCalledOnce()

    fireEvent.mouseDown(document.body)
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
    expect(document.activeElement).toBe(trigger)
  })

  it("closes from a menu-item Escape key", async () => {
    const user = userEvent.setup()
    render(<ActionMenu items={items} />)
    await user.click(screen.getByRole("button", { name: /open menu/i }))
    await user.click(screen.getByRole("menuitem", { name: "Edit" }))

    await user.click(screen.getByRole("button", { name: /open menu/i }))
    const edit = screen.getByRole("menuitem", { name: "Edit" })
    edit.focus()
    await user.keyboard("{Escape}")
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
  })
})

describe("ActionMenu — interactions", () => {
  it("invokes the item's onClick and closes the menu", async () => {
    const onEdit = vi.fn()
    const user = userEvent.setup()
    render(
      <ActionMenu
        items={[
          { label: "Edit", onClick: onEdit },
          { label: "Cancel", onClick: vi.fn() },
        ]}
      />
    )

    await user.click(screen.getByRole("button", { name: /open menu/i }))
    await user.click(screen.getByRole("menuitem", { name: "Edit" }))

    expect(onEdit).toHaveBeenCalledOnce()
    expect(screen.queryByRole("menu")).toBeNull()
  })

  it("does not invoke disabled items", async () => {
    const onClick = vi.fn()
    const user = userEvent.setup()
    render(<ActionMenu items={[{ label: "Disabled", onClick, disabled: true }]} />)

    await user.click(screen.getByRole("button", { name: /open menu/i }))
    await user.click(screen.getByRole("menuitem", { name: "Disabled" }))

    expect(onClick).not.toHaveBeenCalled()
  })
})

describe("ActionMenu — accessibility", () => {
  it("has no axe violations when closed", async () => {
    const { container } = render(<ActionMenu items={items} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it("has no axe violations when open", async () => {
    const user = userEvent.setup()
    const { container } = render(<ActionMenu items={items} />)
    await user.click(screen.getByRole("button", { name: /open menu/i }))
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
