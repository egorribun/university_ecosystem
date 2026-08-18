/**
 * Smoke + interaction tests for EventsShortcutsOverlay.
 *
 * Tests focus on:
 * 1. Component renders null when closed (default state).
 * 2. The "?" keypress opens the overlay.
 * 3. "Escape" closes the overlay when open.
 * 4. Clicking the backdrop closes the overlay.
 * 5. Input elements do NOT trigger the overlay toggle (guard logic).
 */
import { render, screen, fireEvent } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { EventsShortcutsOverlay } from "../EventsShortcutsOverlay"

function renderOverlay() {
  return render(<EventsShortcutsOverlay />)
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function pressKey(key: string, options: KeyboardEventInit = {}) {
  // Dispatch on document.body (an HTMLElement) so the component's
  // `(e.target as HTMLElement).closest(...)` call works in jsdom.
  // Dispatching on `window` gives a non-Element target that lacks .closest().
  fireEvent.keyDown(document.body, { key, ...options })
}

describe("EventsShortcutsOverlay", () => {
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

  // ── close via keyboard ─────────────────────────────────────────────────────
  it("closes when Escape is pressed while open", () => {
    renderOverlay()
    pressKey("?")
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    pressKey("Escape")
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  // ── toggle behaviour ───────────────────────────────────────────────────────
  it("toggles closed when '?' is pressed a second time", () => {
    renderOverlay()
    pressKey("?")
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    pressKey("?")
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  // ── input guard ────────────────────────────────────────────────────────────
  it("does NOT open when '?' is pressed while an INPUT is focused", () => {
    const { container } = renderOverlay()
    // Attach an input so we can dispatch from it
    const input = document.createElement("input")
    container.appendChild(input)
    input.focus()
    fireEvent.keyDown(input, { key: "?" })
    expect(screen.queryByRole("dialog")).toBeNull()
    container.removeChild(input)
  })

  // ── backdrop click ─────────────────────────────────────────────────────────
  it("closes when the backdrop is clicked", () => {
    renderOverlay()
    pressKey("?")
    const dialog = screen.getByRole("dialog")
    fireEvent.click(dialog) // click the backdrop div
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("keeps the overlay open when its content panel is clicked", () => {
    renderOverlay()
    pressKey("?")

    fireEvent.click(screen.getByRole("document"))

    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })

  it("ignores shortcut keys originating inside another dialog", () => {
    const { container } = renderOverlay()
    const dialog = document.createElement("div")
    dialog.setAttribute("role", "dialog")
    const button = document.createElement("button")
    dialog.appendChild(button)
    container.appendChild(dialog)

    fireEvent.keyDown(button, { key: "?" })

    expect(screen.queryByRole("dialog")).toBe(dialog)
  })

  // ── content ────────────────────────────────────────────────────────────────
  it("renders all shortcut keys when open", () => {
    renderOverlay()
    pressKey("?")
    // All 6 key labels from the shortcuts array
    const expectedKeys = ["J", "K", "Enter", "R", "Esc", "?"]
    for (const key of expectedKeys) {
      expect(screen.getAllByText(key).length).toBeGreaterThan(0)
    }
  })
})
