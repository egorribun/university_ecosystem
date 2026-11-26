/**
 * Smoke + interaction tests for NewsShortcutsOverlay.
 *
 * Mirrors the structure of EventsShortcutsOverlay tests.
 * NewsShortcutsOverlay has one fewer shortcut (no "R" / register)
 * and handles Escape via onKeyDown on the backdrop rather than a global
 * window listener, so that path is also tested here.
 */
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it } from "vitest"
import { NewsShortcutsOverlay } from "../NewsShortcutsOverlay"

function renderOverlay() {
  return render(<NewsShortcutsOverlay />)
}

function pressKey(key: string, options: KeyboardEventInit = {}) {
  // Dispatch on document.body (an HTMLElement) so the component's
  // `(e.target as HTMLElement).closest(...)` call works in jsdom.
  fireEvent.keyDown(document.body, { key, ...options })
}

afterEach(async () => {
  cleanup()
  await act(() => new Promise<void>((resolve) => setTimeout(resolve, 0)))
})

describe("NewsShortcutsOverlay", () => {
  it.each(["?", "{Escape}"])("contains focus and closes with %s from inside", async (key) => {
    const user = userEvent.setup()
    render(
      <>
        <button type="button">News trigger</button>
        <NewsShortcutsOverlay />
        <button type="button">Next action</button>
      </>
    )
    const trigger = screen.getByRole("button", { name: "News trigger" })
    trigger.focus()

    await user.keyboard("?")
    const dialog = screen.getByRole("dialog")
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true), {
      timeout: 1000,
    })
    await user.tab()
    expect(dialog.contains(document.activeElement)).toBe(true)
    await user.tab({ shift: true })
    expect(dialog.contains(document.activeElement)).toBe(true)

    await user.keyboard(key)
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it("provides a close button without dismissing when reading the card", async () => {
    const user = userEvent.setup()
    renderOverlay()
    pressKey("?")
    const dialog = screen.getByRole("dialog")
    expect(dialog).toHaveAccessibleName("Keyboard shortcuts")
    expect(dialog).toHaveAccessibleDescription("Press ? or Esc to close")
    await user.click(within(dialog).getByRole("heading"))
    expect(dialog).toBeInTheDocument()

    const close = within(dialog).getByRole("button", { name: /close|закрыть/i })
    expect(close).toHaveClass("min-h-[44px]", "min-w-[44px]")
    await user.click(close)
    expect(dialog).not.toBeInTheDocument()
  })

  it("does not take over shortcut keys in a different modal", () => {
    render(
      <>
        <div role="dialog" aria-label="Other dialog">
          <button type="button">Other control</button>
        </div>
        <NewsShortcutsOverlay />
      </>
    )
    fireEvent.keyDown(screen.getByRole("button", { name: "Other control" }), { key: "?" })
    expect(screen.getAllByRole("dialog")).toHaveLength(1)
  })

  // ── initial state ──────────────────────────────────────────────────────────
  it("renders nothing by default (overlay is closed)", () => {
    renderOverlay()
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  // ── open via keyboard ──────────────────────────────────────────────────────
  it("opens when '?' is pressed", () => {
    renderOverlay()
    pressKey("?")
    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })

  it("does NOT open when '?' is pressed with Ctrl modifier", () => {
    renderOverlay()
    pressKey("?", { ctrlKey: true })
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("does NOT open when '?' is pressed with Meta modifier", () => {
    renderOverlay()
    pressKey("?", { metaKey: true })
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  // ── close via keyboard (window listener) ───────────────────────────────────
  it("closes when Escape is pressed via window listener while open", () => {
    renderOverlay()
    pressKey("?")
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    pressKey("Escape")
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  // ── close via backdrop onKeyDown ───────────────────────────────────────────
  it("closes when Escape is pressed directly on the backdrop element", () => {
    renderOverlay()
    pressKey("?")
    const dialog = screen.getByRole("dialog")
    fireEvent.keyDown(dialog, { key: "Escape" })
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("stays open when a non-Escape key reaches the backdrop", () => {
    renderOverlay()
    pressKey("?")
    const dialog = screen.getByRole("dialog")

    fireEvent.keyDown(dialog, { key: "Enter" })

    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })

  // ── toggle behaviour ───────────────────────────────────────────────────────
  it("toggles closed when '?' is pressed a second time", () => {
    renderOverlay()
    pressKey("?")
    pressKey("?")
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  // ── input guard ────────────────────────────────────────────────────────────
  it("does NOT open when '?' is pressed inside a TEXTAREA", () => {
    const { container } = renderOverlay()
    const textarea = document.createElement("textarea")
    container.appendChild(textarea)
    textarea.focus()
    fireEvent.keyDown(textarea, { key: "?" })
    expect(screen.queryByRole("dialog")).toBeNull()
    container.removeChild(textarea)
  })

  // ── backdrop click ─────────────────────────────────────────────────────────
  it("closes when the backdrop is clicked", () => {
    renderOverlay()
    pressKey("?")
    const dialog = screen.getByRole("dialog")
    fireEvent.click(dialog)
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  // ── content ────────────────────────────────────────────────────────────────
  it("renders all shortcut keys when open", () => {
    renderOverlay()
    pressKey("?")
    // 5 shortcut keys for News (no "R" key unlike Events)
    const expectedKeys = ["J", "K", "Enter", "Esc", "?"]
    for (const key of expectedKeys) {
      expect(screen.getAllByText(key).length).toBeGreaterThan(0)
    }
  })
})
