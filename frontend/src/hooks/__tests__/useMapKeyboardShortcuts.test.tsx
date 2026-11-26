import { describe, expect, it, vi } from "vitest"
import { renderHook } from "@testing-library/react"
import { useMapKeyboardShortcuts } from "../useMapKeyboardShortcuts"

describe("useMapKeyboardShortcuts hook", () => {
  it.each(["ctrlKey", "metaKey", "altKey"] as const)(
    "leaves %s keyboard chords to the browser",
    (modifier) => {
      const deps = {
        onSelectBuilding: vi.fn(),
        onToggleFullscreen: vi.fn(),
        onFocusSearch: vi.fn(),
        onToggleShortcuts: vi.fn(),
      }
      const { unmount } = renderHook(() => useMapKeyboardShortcuts(deps))
      for (const key of ["1", "f", "F", "/", "?"]) {
        const event = new KeyboardEvent("keydown", {
          key,
          [modifier]: true,
          bubbles: true,
          cancelable: true,
        })
        document.body.dispatchEvent(event)
        expect(event.defaultPrevented).toBe(false)
      }
      for (const callback of Object.values(deps)) expect(callback).not.toHaveBeenCalled()
      unmount()
    }
  )

  it("ignores events already consumed by a control or still composing", () => {
    const deps = {
      onSelectBuilding: vi.fn(),
      onToggleFullscreen: vi.fn(),
      onFocusSearch: vi.fn(),
      onToggleShortcuts: vi.fn(),
    }
    const { unmount } = renderHook(() => useMapKeyboardShortcuts(deps))
    const consumed = new KeyboardEvent("keydown", {
      key: "f",
      bubbles: true,
      cancelable: true,
    })
    consumed.preventDefault()
    document.body.dispatchEvent(consumed)
    const composing = new KeyboardEvent("keydown", {
      key: "f",
      isComposing: true,
      bubbles: true,
      cancelable: true,
    })
    document.body.dispatchEvent(composing)
    expect(composing.defaultPrevented).toBe(false)
    for (const callback of Object.values(deps)) expect(callback).not.toHaveBeenCalled()
    unmount()
  })

  it.each(["true", "", "plaintext-only", "TRUE"])(
    "preserves typing inside contenteditable=%j and its descendants",
    (value) => {
      const deps = {
        onSelectBuilding: vi.fn(),
        onToggleFullscreen: vi.fn(),
        onFocusSearch: vi.fn(),
        onToggleShortcuts: vi.fn(),
      }
      const { unmount } = renderHook(() => useMapKeyboardShortcuts(deps))
      const editor = document.createElement("div")
      editor.setAttribute("contenteditable", value)
      const span = document.createElement("span")
      editor.appendChild(span)
      document.body.appendChild(editor)
      try {
        for (const target of [editor, span]) {
          for (const key of ["1", "f", "/", "?"]) {
            const event = new KeyboardEvent("keydown", {
              key,
              bubbles: true,
              cancelable: true,
            })
            target.dispatchEvent(event)
            expect(event.defaultPrevented).toBe(false)
          }
        }
        for (const callback of Object.values(deps)) expect(callback).not.toHaveBeenCalled()
      } finally {
        editor.remove()
        unmount()
      }
    }
  )

  it("keeps shortcuts in a noneditable island inside an editor", () => {
    const deps = {
      onSelectBuilding: vi.fn(),
      onToggleFullscreen: vi.fn(),
      onFocusSearch: vi.fn(),
      onToggleShortcuts: vi.fn(),
    }
    const { unmount } = renderHook(() => useMapKeyboardShortcuts(deps))
    const editor = document.createElement("div")
    editor.setAttribute("contenteditable", "true")
    const island = document.createElement("div")
    island.setAttribute("contenteditable", "false")
    const span = document.createElement("span")
    island.appendChild(span)
    editor.appendChild(island)
    document.body.appendChild(editor)
    try {
      const event = new KeyboardEvent("keydown", {
        key: "f",
        bubbles: true,
        cancelable: true,
      })
      span.dispatchEvent(event)
      expect(event.defaultPrevented).toBe(true)
      expect(deps.onToggleFullscreen).toHaveBeenCalledOnce()
    } finally {
      editor.remove()
      unmount()
    }
  })

  it.each(["dialog", "alertdialog", "native"])(
    "does not run map commands from a different %s",
    (kind) => {
      const deps = {
        onSelectBuilding: vi.fn(),
        onToggleFullscreen: vi.fn(),
        onFocusSearch: vi.fn(),
        onToggleShortcuts: vi.fn(),
      }
      const { unmount } = renderHook(() => useMapKeyboardShortcuts(deps))
      const dialog = document.createElement(kind === "native" ? "dialog" : "div")
      if (kind === "native") dialog.setAttribute("open", "")
      else dialog.setAttribute("role", kind)
      const button = document.createElement("button")
      dialog.appendChild(button)
      document.body.appendChild(dialog)
      try {
        button.focus()
        for (const key of ["1", "f", "/", "?"]) {
          const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true })
          button.dispatchEvent(event)
          expect(event.defaultPrevented).toBe(false)
        }
        for (const callback of Object.values(deps)) expect(callback).not.toHaveBeenCalled()
      } finally {
        dialog.remove()
        unmount()
      }
    }
  )

  it("only lets the help shortcut toggle the map's own dialog", () => {
    const deps = {
      onSelectBuilding: vi.fn(),
      onToggleFullscreen: vi.fn(),
      onFocusSearch: vi.fn(),
      onToggleShortcuts: vi.fn(),
    }
    const { unmount } = renderHook(() => useMapKeyboardShortcuts(deps))
    const dialog = document.createElement("div")
    dialog.setAttribute("role", "dialog")
    dialog.setAttribute("data-map-shortcuts-dialog", "")
    const button = document.createElement("button")
    dialog.appendChild(button)
    document.body.appendChild(dialog)
    try {
      button.focus()
      for (const key of ["f", "1", "/"]) {
        const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true })
        button.dispatchEvent(event)
        expect(event.defaultPrevented).toBe(false)
      }
      expect(deps.onSelectBuilding).not.toHaveBeenCalled()
      expect(deps.onToggleFullscreen).not.toHaveBeenCalled()
      expect(deps.onFocusSearch).not.toHaveBeenCalled()

      for (const [key, shiftKey] of [
        ["?", false],
        ["/", true],
      ] as const) {
        const event = new KeyboardEvent("keydown", {
          key,
          shiftKey,
          bubbles: true,
          cancelable: true,
        })
        button.dispatchEvent(event)
        expect(event.defaultPrevented).toBe(true)
      }
      expect(deps.onToggleShortcuts).toHaveBeenCalledTimes(2)
    } finally {
      dialog.remove()
      unmount()
    }
  })

  it("registers window listeners and handles shortcuts", () => {
    const deps = {
      onSelectBuilding: vi.fn(),
      onToggleFullscreen: vi.fn(),
      onFocusSearch: vi.fn(),
      onToggleShortcuts: vi.fn(),
    }

    const { unmount } = renderHook(() => useMapKeyboardShortcuts(deps))

    // Press '1' to select first building
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "1", bubbles: true }))
    expect(deps.onSelectBuilding).toHaveBeenCalledWith("ГУК")

    // Press 'f'
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "f", bubbles: true }))
    expect(deps.onToggleFullscreen).toHaveBeenCalled()

    // Press '/'
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "/", bubbles: true }))
    expect(deps.onFocusSearch).toHaveBeenCalled()

    // Press '?'
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "?", bubbles: true }))
    expect(deps.onToggleShortcuts).toHaveBeenCalled()

    // Press '0' (should not trigger anything)
    deps.onSelectBuilding.mockClear()
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "0", bubbles: true }))
    expect(deps.onSelectBuilding).not.toHaveBeenCalled()

    // Simulate keydown on interactive tag (should skip)
    deps.onSelectBuilding.mockClear()
    const input = document.createElement("input")
    document.body.appendChild(input)
    input.focus()
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "1", bubbles: true }))
    expect(deps.onSelectBuilding).not.toHaveBeenCalled()
    document.body.removeChild(input)

    // Press shift + '/'
    deps.onToggleShortcuts.mockClear()
    document.body.dispatchEvent(
      new KeyboardEvent("keydown", { key: "/", shiftKey: true, bubbles: true })
    )
    expect(deps.onToggleShortcuts).toHaveBeenCalled()

    // Simulate keydown on contenteditable element
    deps.onSelectBuilding.mockClear()
    const editable = document.createElement("div")
    editable.setAttribute("contenteditable", "true")
    document.body.appendChild(editable)
    editable.dispatchEvent(new KeyboardEvent("keydown", { key: "1", bubbles: true }))
    expect(deps.onSelectBuilding).not.toHaveBeenCalled()
    document.body.removeChild(editable)

    // Simulate keydown with null target (using manual event handler capture)
    deps.onSelectBuilding.mockClear()
    const addEventListenerSpy = vi.spyOn(window, "addEventListener")
    const { unmount: unmount2 } = renderHook(() => useMapKeyboardShortcuts(deps))
    const handler = addEventListenerSpy.mock.calls.find(
      (call) => (call[0] as string) === "keydown"
    )?.[1] as Function
    expect(handler).toBeDefined()
    // Invoke handler with null target event structure
    handler({
      key: "1",
      target: null,
      preventDefault: vi.fn(),
    })
    expect(deps.onSelectBuilding).not.toHaveBeenCalled()

    addEventListenerSpy.mockRestore()
    unmount2()
    unmount()
  })
})
