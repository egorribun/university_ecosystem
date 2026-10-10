import { act, cleanup, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { useScrollToElement } from "@/hooks/useScrollToElement"

describe("useScrollToElement", () => {
  let frames: FrameRequestCallback[]
  let targets: HTMLDivElement[]

  function targetWithId(id: string) {
    const target = document.createElement("div")
    target.id = id
    target.scrollIntoView = vi.fn()
    targets.push(target)
    return target
  }

  function flushFrame() {
    const callbacks = frames.splice(0)
    const errors: unknown[] = []
    try {
      act(() => {
        for (const callback of callbacks) {
          try {
            callback(0)
          } catch (error) {
            errors.push(error)
          }
        }
      })
    } catch (error) {
      errors.push(error)
    }
    if (errors.length) throw new AggregateError(errors, "Owned frame callbacks failed")
  }

  beforeEach(() => {
    frames = []
    targets = []
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      frames.push(callback)
      return frames.length
    })
  })

  afterEach(() => {
    const errors: unknown[] = []
    // Attempt each stage even if unmounting or a queued callback fails.
    // The hook does not cancel frames, so execute them before restoring the spy.
    const steps = [
      cleanup,
      flushFrame,
      ...targets.map((target) => () => target.remove()),
      () => vi.restoreAllMocks(),
    ]
    for (const step of steps) {
      try {
        step()
      } catch (error) {
        errors.push(error)
      }
    }
    if (errors.length) throw new AggregateError(errors, "useScrollToElement fixture cleanup failed")
  })

  it.each([
    { name: "omitted options", useScroll: (id: string) => useScrollToElement(id) },
    { name: "undefined options", useScroll: (id: string) => useScrollToElement(id, undefined) },
    { name: "empty options", useScroll: (id: string) => useScrollToElement(id, {}) },
    {
      name: "undefined option properties",
      useScroll: (id: string) => useScrollToElement(id, { behavior: undefined, block: undefined }),
    },
  ])("scrolls the requested target smoothly to the center with $name", ({ useScroll }) => {
    const target = targetWithId("current-lesson")
    const other = targetWithId("other-lesson")
    document.body.appendChild(other)
    const { rerender } = renderHook(({ id }) => useScroll(id), {
      initialProps: { id: target.id },
    })

    // Layout can insert the target between the effect and the next frame.
    expect(frames).toHaveLength(1)
    expect(target.scrollIntoView).not.toHaveBeenCalled()
    document.body.appendChild(target)
    flushFrame()
    expect(target.scrollIntoView).toHaveBeenCalledExactlyOnceWith({
      behavior: "smooth",
      block: "center",
    })
    expect(other.scrollIntoView).not.toHaveBeenCalled()

    rerender({ id: target.id })
    expect(frames).toHaveLength(0)
    expect(target.scrollIntoView).toHaveBeenCalledTimes(1)
  })

  it("scrolls each new target once with configured alignment", () => {
    const first = targetWithId("lesson-1")
    const second = targetWithId("lesson-2")
    document.body.append(first, second)

    const { rerender } = renderHook(
      ({ id, behavior }) => useScrollToElement(id, { behavior, block: "start" }),
      { initialProps: { id: null as string | null, behavior: "auto" as ScrollBehavior } }
    )
    expect(frames).toHaveLength(0)

    rerender({ id: first.id, behavior: "auto" })
    expect(frames).toHaveLength(1)
    flushFrame()
    expect(first.scrollIntoView).toHaveBeenCalledExactlyOnceWith({
      behavior: "auto",
      block: "start",
    })

    rerender({ id: first.id, behavior: "smooth" })
    expect(frames).toHaveLength(0)

    rerender({ id: second.id, behavior: "smooth" })
    expect(frames).toHaveLength(1)
    flushFrame()
    expect(second.scrollIntoView).toHaveBeenCalledExactlyOnceWith({
      behavior: "smooth",
      block: "start",
    })
    expect(first.scrollIntoView).toHaveBeenCalledTimes(1)

    rerender({ id: "missing", behavior: "smooth" })
    expect(frames).toHaveLength(1)
    flushFrame()
    expect(first.scrollIntoView).toHaveBeenCalledTimes(1)
    expect(second.scrollIntoView).toHaveBeenCalledTimes(1)
  })
})
