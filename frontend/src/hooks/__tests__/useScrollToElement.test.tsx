import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { useScrollToElement } from "@/hooks/useScrollToElement"

describe("useScrollToElement", () => {
  let frame: FrameRequestCallback | undefined

  beforeEach(() => {
    frame = undefined
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      frame = callback
      return 1
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("scrolls each new target once with configured alignment", () => {
    const target = document.createElement("div")
    target.id = "lesson-1"
    target.scrollIntoView = vi.fn()
    document.body.appendChild(target)

    const { rerender } = renderHook(
      ({ id, behavior }) => useScrollToElement(id, { behavior, block: "start" }),
      { initialProps: { id: null as string | null, behavior: "auto" as ScrollBehavior } }
    )
    expect(frame).toBeUndefined()

    rerender({ id: "lesson-1", behavior: "auto" })
    act(() => frame?.(0))
    expect(target.scrollIntoView).toHaveBeenCalledWith({ behavior: "auto", block: "start" })

    frame = undefined
    rerender({ id: "lesson-1", behavior: "smooth" })
    expect(frame).toBeUndefined()

    rerender({ id: "missing", behavior: "smooth" })
    expect(() => act(() => frame?.(1))).not.toThrow()
    document.body.removeChild(target)
  })
})
