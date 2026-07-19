import { describe, expect, it, vi } from "vitest"
import { renderHook } from "@testing-library/react"
import { useMapKeyboardShortcuts } from "../useMapKeyboardShortcuts"

describe("useMapKeyboardShortcuts hook", () => {
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
