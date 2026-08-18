/**
 * Smoke + interaction tests for NewsShortcutsOverlay.
 *
 * Mirrors the structure of EventsShortcutsOverlay tests.
 * NewsShortcutsOverlay has one fewer shortcut (no "R" / register)
 * and handles Escape via onKeyDown on the backdrop rather than a global
 * window listener, so that path is also tested here.
 */
import { render, screen, fireEvent } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { NewsShortcutsOverlay } from "../NewsShortcutsOverlay"

function renderOverlay() {
  return render(<NewsShortcutsOverlay />)
}

function pressKey(key: string, options: KeyboardEventInit = {}) {
  // Dispatch on document.body (an HTMLElement) so the component's
  // `(e.target as HTMLElement).closest(...)` call works in jsdom.
  fireEvent.keyDown(document.body, { key, ...options })
}

describe("NewsShortcutsOverlay", () => {
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
