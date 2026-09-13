import { describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
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
    expect(trigger.id).not.toBe("")
  })

  it("uses a custom aria-label when supplied", () => {
    render(<ActionMenu items={items} ariaLabel="More actions" />)
    expect(screen.getByRole("button", { name: /more actions/i })).toBeInTheDocument()
  })

  it("keeps the trigger and menu items at least 44px tall", async () => {
    const user = userEvent.setup()
    render(<ActionMenu items={items} />)
    const trigger = screen.getByRole("button", { name: /open menu/i })
    expect(trigger).toHaveClass("h-11", "w-11")

    await user.click(trigger)
    for (const item of screen.getAllByRole("menuitem")) {
      expect(item).toHaveClass("min-h-11")
    }
  })

  it("forwards stable ids, data markers, disabled state, and opt-in initial focus", async () => {
    const user = userEvent.setup()
    const { rerender } = render(
      <ActionMenu
        items={items}
        triggerId="article-menu-trigger"
        menuId="article-menu"
        disabled
        autoFocusFirstItem
        triggerDataAttributes={{ "data-card-menu-trigger": "true" }}
        menuDataAttributes={{ "data-card-menu": "true" }}
      />
    )
    const disabledTrigger = screen.getByRole("button", { name: /open menu/i })
    expect(disabledTrigger).toBeDisabled()
    expect(disabledTrigger).toHaveAttribute("id", "article-menu-trigger")
    expect(disabledTrigger).toHaveAttribute("data-card-menu-trigger", "true")
    await user.click(disabledTrigger)
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()

    rerender(
      <ActionMenu
        items={items}
        triggerId="article-menu-trigger"
        menuId="article-menu"
        autoFocusFirstItem
        triggerDataAttributes={{ "data-card-menu-trigger": "true" }}
        menuDataAttributes={{ "data-card-menu": "true" }}
      />
    )
    await user.click(screen.getByRole("button", { name: /open menu/i }))
    expect(screen.getByRole("menu")).toHaveAttribute("id", "article-menu")
    expect(screen.getByRole("menu")).toHaveAttribute("aria-labelledby", "article-menu-trigger")
    expect(screen.getByRole("menu")).toHaveAttribute("data-card-menu", "true")
    expect(screen.getAllByRole("menuitem")[0]).toHaveFocus()
  })

  it("derives the missing ARIA counterpart from either caller-supplied id", async () => {
    const user = userEvent.setup()
    const { unmount } = render(<ActionMenu items={items} triggerId="article-actions" />)

    const trigger = screen.getByRole("button", { name: /open menu/i })
    await user.click(trigger)
    expect(trigger).toHaveAttribute("aria-controls", "article-actions-menu")
    expect(screen.getByRole("menu")).toHaveAttribute("id", "article-actions-menu")
    unmount()

    render(<ActionMenu items={items} menuId="account-actions" />)
    const derivedTrigger = screen.getByRole("button", { name: /open menu/i })
    expect(derivedTrigger).toHaveAttribute("id", "account-actions-button")
    await user.click(derivedTrigger)
    expect(screen.getByRole("menu")).toHaveAttribute("aria-labelledby", "account-actions-button")
  })
})

describe("ActionMenu — open + close", () => {
  it("lets a closed trigger bubble a cancelable Escape to its parent", () => {
    const parentKeyDown = vi.fn()
    render(
      <div role="toolbar" aria-label="Actions boundary" onKeyDown={parentKeyDown}>
        <ActionMenu items={items} />
      </div>
    )

    const trigger = screen.getByRole("button", { name: /open menu/i })
    trigger.focus()
    const dispatched = fireEvent.keyDown(trigger, {
      key: "Escape",
      bubbles: true,
      cancelable: true,
    })

    expect(dispatched).toBe(true)
    expect(parentKeyDown).toHaveBeenCalledOnce()
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
  })

  it("opens the menu on click and exposes role='menu'", async () => {
    const user = userEvent.setup()
    render(<ActionMenu items={items} />)
    await user.click(screen.getByRole("button", { name: /open menu/i }))

    const menu = screen.getByRole("menu")
    const trigger = screen.getByRole("button", { name: /open menu/i })
    expect(menu).toBeInTheDocument()
    expect(menu.id).not.toBe("")
    expect(trigger).toHaveAttribute("aria-controls", menu.id)
    expect(menu).toHaveAttribute("aria-labelledby", trigger.id)
    expect(screen.getAllByRole("menuitem")).toHaveLength(items.length)
    expect(screen.getByRole("button", { name: /open menu/i })).toHaveAttribute(
      "aria-expanded",
      "true"
    )
  })

  it("closes on Escape", async () => {
    const user = userEvent.setup()
    const parentKeyDown = vi.fn()
    render(
      <div role="toolbar" aria-label="Actions boundary" onKeyDown={parentKeyDown}>
        <ActionMenu items={items} />
      </div>
    )
    const trigger = screen.getByRole("button", { name: /open menu/i })
    await user.click(trigger)
    expect(screen.getByRole("menu")).toBeInTheDocument()

    const dispatched = fireEvent.keyDown(trigger, {
      key: "Escape",
      bubbles: true,
      cancelable: true,
    })
    expect(dispatched).toBe(false)
    expect(parentKeyDown).not.toHaveBeenCalled()
    expect(screen.queryByRole("menu")).toBeNull()
    expect(trigger).toHaveFocus()
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
    fireEvent.keyDown(edit, { key: "ArrowDown" })
    expect(remove).toHaveFocus()
    fireEvent.keyDown(remove, { key: "ArrowDown" })
    expect(edit).toHaveFocus()
    fireEvent.keyDown(edit, { key: "ArrowUp" })
    expect(remove).toHaveFocus()

    fireEvent.mouseDown(document.body)
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
    expect(document.activeElement).toBe(trigger)
  })

  it("closes from a menu-item Escape key", async () => {
    const user = userEvent.setup()
    const parentKeyDown = vi.fn()
    render(
      <div role="toolbar" aria-label="Actions boundary" onKeyDown={parentKeyDown}>
        <ActionMenu items={items} />
      </div>
    )
    await user.click(screen.getByRole("button", { name: /open menu/i }))
    await user.click(screen.getByRole("menuitem", { name: "Edit" }))

    await user.click(screen.getByRole("button", { name: /open menu/i }))
    const edit = screen.getByRole("menuitem", { name: "Edit" })
    edit.focus()
    const dispatched = fireEvent.keyDown(edit, { key: "Escape", cancelable: true })
    expect(dispatched).toBe(false)
    expect(parentKeyDown).not.toHaveBeenCalled()
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: /open menu/i })).toHaveFocus()
  })

  it("closes an open menu when the trigger becomes disabled", async () => {
    const user = userEvent.setup()
    const { rerender } = render(<ActionMenu items={items} />)
    const trigger = screen.getByRole("button", { name: /open menu/i })

    await user.click(trigger)
    expect(screen.getByRole("menu")).toBeInTheDocument()
    rerender(<ActionMenu items={items} disabled />)

    expect(trigger).toBeDisabled()
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument())
  })

  it("derives unique stable relationships for multiple menus without caller ids", async () => {
    const user = userEvent.setup()
    render(
      <>
        <ActionMenu items={items} ariaLabel="First actions" />
        <ActionMenu items={items} ariaLabel="Second actions" />
      </>
    )
    const firstTrigger = screen.getByRole("button", { name: "First actions" })
    const secondTrigger = screen.getByRole("button", { name: "Second actions" })
    expect(firstTrigger.id).not.toBe(secondTrigger.id)

    await user.click(firstTrigger)
    const firstMenu = screen.getByRole("menu")
    expect(firstTrigger).toHaveAttribute("aria-controls", firstMenu.id)
    expect(firstMenu).toHaveAttribute("aria-labelledby", firstTrigger.id)
  })

  it("keeps the menu open for an unrelated menu-item key", async () => {
    const user = userEvent.setup()
    render(<ActionMenu items={items} />)
    await user.click(screen.getByRole("button", { name: /open menu/i }))
    const edit = screen.getByRole("menuitem", { name: "Edit" })

    fireEvent.keyDown(edit, { key: "Tab" })

    expect(screen.getByRole("menu")).toBeInTheDocument()
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
    const disabledItem = screen.getByRole("menuitem", { name: "Disabled" })
    disabledItem.removeAttribute("disabled")
    fireEvent.click(disabledItem)

    expect(onClick).not.toHaveBeenCalled()
    expect(screen.getByRole("menu")).toBeInTheDocument()
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
