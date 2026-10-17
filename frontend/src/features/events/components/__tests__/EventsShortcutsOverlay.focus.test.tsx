import { StrictMode } from "react"
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"
import { Dialog } from "@/components/ui/Dialog"
import { EventsShortcutsOverlay } from "../EventsShortcutsOverlay"

// focus-trap restores focus on the next task. Drain its cleanup task even after
// an assertion failure, so no delayed callback leaks into another test.
afterEach(async () => {
  try {
    cleanup()
  } finally {
    await act(() => new Promise<void>((resolve) => setTimeout(resolve, 0)))
  }
})

function renderOverlay() {
  const view = render(
    <StrictMode>
      <button type="button">Events trigger</button>
      <EventsShortcutsOverlay />
      <button type="button">Following control</button>
    </StrictMode>
  )
  const trigger = screen.getByRole("button", { name: "Events trigger" })
  trigger.focus()
  return { ...view, trigger, user: userEvent.setup() }
}

describe("EventsShortcutsOverlay keyboard focus", () => {
  it("moves focus into its modal and contains forward and backward Tab", async () => {
    const { user } = renderOverlay()
    await user.keyboard("?")
    const dialog = screen.getByRole("dialog")

    await waitFor(() => expect(dialog).toHaveFocus())
    await user.tab()
    expect(dialog).toHaveFocus()
    await user.tab({ shift: true })
    expect(dialog).toHaveFocus()
  })

  it.each(["{Escape}", "?"])("closes from its focused dialog with %s", async (key) => {
    const { trigger, user } = renderOverlay()
    await user.keyboard("?")
    const dialog = screen.getByRole("dialog")
    // Exercise the existing guard separately from missing initial focus.
    dialog.focus()
    expect(dialog).toHaveFocus()
    await user.keyboard(key)

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it("returns focus to the opener after a backdrop click", async () => {
    const { trigger, user } = renderOverlay()
    await user.keyboard("?")
    const dialog = screen.getByRole("dialog")
    dialog.focus()
    await user.click(dialog)

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it("names and describes the modal using its visible title and instructions", async () => {
    const { user } = renderOverlay()
    await user.keyboard("?")
    const dialog = screen.getByRole("dialog")
    const heading = screen.getByRole("heading", { level: 2 })
    const instructions = dialog.querySelector("p")!

    expect(heading.id).not.toBe("")
    expect(dialog).toHaveAttribute("aria-labelledby", heading.id)
    expect(instructions.id).not.toBe("")
    expect(dialog).toHaveAttribute("aria-describedby", instructions.id)
    expect(dialog).toHaveAttribute("aria-modal", "true")
  })

  it.each(["input", "textarea"] as const)("leaves %s editing keys alone", async (tag) => {
    const { container, user } = renderOverlay()
    const editor = document.createElement(tag)
    container.append(editor)
    editor.focus()
    await user.keyboard("?{Escape}")

    expect(editor).toHaveValue("?")
    expect(editor).toHaveFocus()
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it.each(["dialog", "aria-dialog"])("ignores keys from an unrelated %s", async (kind) => {
    const { container, user } = renderOverlay()
    const dialog = document.createElement(kind === "dialog" ? "dialog" : "div")
    if (kind === "dialog") dialog.setAttribute("open", "")
    else dialog.setAttribute("role", "dialog")
    const control = document.createElement("button")
    control.textContent = "Other dialog control"
    dialog.append(control)
    container.append(dialog)
    control.focus()
    await user.keyboard("?{Escape}")

    expect(screen.queryAllByRole("dialog")).toEqual([dialog])
    expect(control).toHaveFocus()
  })

  it("leaves contenteditable typing alone", async () => {
    const { container, user } = renderOverlay()
    const editor = document.createElement("div")
    editor.setAttribute("contenteditable", "true")
    editor.tabIndex = 0
    // JSDOM lacks this browser-computed property. Model it only on the real
    // editable element, as the existing events keyboard-navigation tests do.
    Object.defineProperty(editor, "isContentEditable", { value: true, configurable: true })
    container.append(editor)
    editor.focus()
    await user.keyboard("?{Escape}")

    expect(editor).toHaveTextContent("?")
    expect(editor).toHaveFocus()
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("does not consume shortcuts belonging to another active modal", async () => {
    const user = userEvent.setup()
    const closeOtherDialog = vi.fn()
    const content = (otherOpen: boolean) => (
      <StrictMode>
        <button type="button">Events trigger</button>
        <EventsShortcutsOverlay />
        <Dialog open={otherOpen} onClose={closeOtherDialog} title="Another modal">
          Other content
        </Dialog>
      </StrictMode>
    )
    const view = render(content(false))
    screen.getByRole("button", { name: "Events trigger" }).focus()
    await user.keyboard("?")
    const help = screen.getByRole("dialog")
    await waitFor(() => expect(help).toHaveFocus())
    view.rerender(content(true))
    const other = screen.getByRole("dialog", { name: "Another modal" })
    await waitFor(() => expect(other).toContainElement(document.activeElement as HTMLElement))

    await user.keyboard("?")
    expect(help).toBeInTheDocument()
    await user.keyboard("{Escape}")
    expect(closeOtherDialog).toHaveBeenCalledOnce()
    expect(help).toBeInTheDocument()
  })

  it("preserves modifier and non-shortcut key behavior while focused inside", async () => {
    const { trigger, user } = renderOverlay()
    await user.keyboard("{Control>}?{/Control}{Meta>}?{/Meta}{Escape}")
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()

    await user.keyboard("{Alt>}?{/Alt}")
    const dialog = screen.getByRole("dialog")
    dialog.focus()
    await user.keyboard("{Control>}?{/Control}{Meta>}?{/Meta}jk{Enter}r")
    expect(dialog).toBeInTheDocument()

    await user.keyboard("{Shift>}?{/Shift}")
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it("removes its global keyboard listener when unmounted", async () => {
    const { unmount, user } = renderOverlay()
    unmount()
    const event = new KeyboardEvent("keydown", { key: "?", bubbles: true, cancelable: true })
    fireEvent(document.body, event)
    expect(event.defaultPrevented).toBe(false)
    await user.tab()
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it.each([false, true])(
    "releases active focus ownership on unmount (initial task ran: %s)",
    async (settle) => {
      const { unmount } = renderOverlay()
      fireEvent.keyDown(document.activeElement!, { key: "?" })
      if (settle) await waitFor(() => expect(screen.getByRole("dialog")).toHaveFocus())
      unmount()

      render(<button type="button">Next page</button>)
      const next = screen.getByRole("button", { name: "Next page" })
      next.focus()
      await act(() => new Promise<void>((resolve) => setTimeout(resolve, 0)))

      expect(next).toHaveFocus()
      const event = new KeyboardEvent("keydown", { key: "?", bubbles: true, cancelable: true })
      fireEvent(next, event)
      expect(event.defaultPrevented).toBe(false)
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    }
  )
})
