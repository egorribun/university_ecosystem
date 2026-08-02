import { act, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { createElement, type ReactNode } from "react"

const motionState = vi.hoisted(() => ({
  props: [] as Array<Record<string, unknown>>,
}))

vi.mock("framer-motion", () => ({
  m: {
    div: (props: Record<string, unknown> & { children?: ReactNode }) => {
      motionState.props.push(props)
      return createElement("div", { "data-testid": "motion-content" }, props.children)
    },
  },
}))

type ObserverHarness = {
  callback: IntersectionObserverCallback
  options: IntersectionObserverInit | undefined
  observe: ReturnType<typeof vi.fn>
  disconnect: ReturnType<typeof vi.fn>
}

const observers: ObserverHarness[] = []

class MockIntersectionObserver {
  readonly root = null
  readonly rootMargin: string
  readonly thresholds: readonly number[] = []
  readonly observe = vi.fn()
  readonly disconnect = vi.fn()
  readonly unobserve = vi.fn()
  readonly takeRecords = vi.fn(() => [])
  readonly callback: IntersectionObserverCallback
  readonly options: IntersectionObserverInit | undefined

  constructor(callback: IntersectionObserverCallback, options?: IntersectionObserverInit) {
    this.callback = callback
    this.options = options
    this.rootMargin = options?.rootMargin ?? ""
    observers.push(this)
  }
}

vi.stubGlobal("IntersectionObserver", MockIntersectionObserver)

import { ScrollReveal } from "@/components/motion/ScrollReveal"

function trigger(index: number, entries: IntersectionObserverEntry[]) {
  const observer = observers[index]!
  act(() => observer.callback(entries, observer as unknown as IntersectionObserver))
}

describe("ScrollReveal", () => {
  beforeEach(() => {
    observers.length = 0
    motionState.props.length = 0
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it("starts hidden, ignores empty/non-intersecting entries, then disconnects on reveal", () => {
    const { unmount } = render(
      <ScrollReveal
        className="reveal"
        width="fit-content"
        viewportMargin="10px"
        delay={0.2}
        duration={0.4}
      >
        <span>revealed content</span>
      </ScrollReveal>
    )

    const observer = observers[0]!
    expect(observer.options).toEqual({ rootMargin: "10px" })
    expect(observer.observe).toHaveBeenCalledWith(
      screen.getByTestId("motion-content").parentElement
    )
    expect(motionState.props.at(-1)?.animate).toBe("hidden")

    trigger(0, [])
    trigger(0, [{ isIntersecting: false } as IntersectionObserverEntry])
    expect(observer.disconnect).not.toHaveBeenCalled()

    trigger(0, [{ isIntersecting: true } as IntersectionObserverEntry])
    expect(observer.disconnect).toHaveBeenCalled()
    expect(motionState.props.at(-1)?.animate).toBe("visible")
    expect(screen.getByTestId("motion-content").parentElement).toHaveClass("reveal")
    expect(screen.getByTestId("motion-content").parentElement).toHaveStyle({ width: "fit-content" })

    unmount()
    expect(observer.disconnect).toHaveBeenCalled()
  })

  it.each([
    ["slide", "up", "y", 1],
    ["slide", "down", "y", -1],
    ["fade", "left", "x", 1],
    ["fade", "right", "x", -1],
  ] as const)("builds the %s/%s directional variants", (mode, direction, axis, sign) => {
    render(
      <ScrollReveal mode={mode} direction={direction}>
        directional
      </ScrollReveal>
    )

    const variants = motionState.props.at(-1)?.variants as {
      hidden: Record<string, unknown>
      visible: Record<string, unknown>
    }
    expect(variants.hidden[axis]).toBe(sign === 1 ? "20px" : "-20px")
    expect(variants.visible[axis]).toBe(0)
    expect(variants.hidden.opacity).toBe(0)
    expect(variants.visible.opacity).toBe(1)
    expect(motionState.props.at(-1)?.transition).toEqual(
      expect.objectContaining({ duration: expect.any(Number), delay: 0 })
    )
  })

  it("builds pop and scale variants with spring transitions", () => {
    const { rerender } = render(
      <ScrollReveal mode="pop" delay={0.3}>
        pop
      </ScrollReveal>
    )
    let props = motionState.props.at(-1)!
    expect((props.variants as { hidden: Record<string, unknown> }).hidden.scale).toBe(0.94)
    expect(props.transition).toEqual(expect.objectContaining({ delay: 0.3, type: "spring" }))

    rerender(
      <ScrollReveal mode="scale" delay={0.4}>
        scale
      </ScrollReveal>
    )
    props = motionState.props.at(-1)!
    expect((props.variants as { hidden: Record<string, unknown> }).hidden.scale).toBe(0.96)
    expect(props.transition).toEqual(expect.objectContaining({ delay: 0.4, type: "spring" }))
  })

  it("supports an unhandled direction without adding an offset and cleans up unseen observers", () => {
    const { unmount } = render(
      <ScrollReveal mode={"slide"} direction={"diagonal" as never} viewportMargin="0px">
        diagonal
      </ScrollReveal>
    )

    const props = motionState.props.at(-1)!
    const hidden = (props.variants as { hidden: Record<string, unknown> }).hidden
    expect(hidden).toEqual({ opacity: 0, filter: "blur(0.5rem)" })
    unmount()
    expect(observers[0]?.disconnect).toHaveBeenCalledOnce()
  })

  it("stops observing after becoming visible", () => {
    const { rerender } = render(<ScrollReveal>once</ScrollReveal>)
    trigger(0, [{ isIntersecting: true } as IntersectionObserverEntry])
    const count = observers.length

    rerender(<ScrollReveal>still visible</ScrollReveal>)
    expect(observers).toHaveLength(count)
    expect(motionState.props.at(-1)?.animate).toBe("visible")
  })
})
