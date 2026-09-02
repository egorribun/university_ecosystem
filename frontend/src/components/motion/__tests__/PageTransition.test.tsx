import { act, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"

const motionState = vi.hoisted(() => ({
  initialValues: [] as unknown[],
  props: [] as Array<Record<string, unknown>>,
  lazyFeatures: [] as unknown[],
}))

// The animated branch only commits after the async `import("framer-motion")` →
// setState chain resolves. waitFor polls inside act(), absorbing the
// module-level motionModulePromise cache timing variance across tests.
const WILL_CHANGE = ".will-change-\\[transform\\,opacity\\,filter\\]"

const expectAnimatedChild = async (text: string) =>
  waitFor(() => {
    const node = screen.getByText(text)
    // animated branch (LazyMotion + m.div) attaches the will-change wrapper;
    // the reduced-motion fallback does not — so this asserts the animated commit
    expect(node.closest(WILL_CHANGE)).toBeInTheDocument()
    return node
  })

vi.mock("framer-motion", async () => {
  const { createElement, Fragment } = await import("react")
  const base = (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
  const BaseDiv = base.m.div
  if (!BaseDiv) throw new Error("framer-motion mock did not provide m.div")
  const CapturingDiv = (props: Record<string, unknown>) => {
    motionState.initialValues.push(props.initial)
    motionState.props.push(props)
    return createElement(BaseDiv, props)
  }
  const CapturingLazyMotion = ({
    children,
    features,
  }: {
    children?: ReactNode
    features?: unknown
  }) => {
    motionState.lazyFeatures.push(features)
    return createElement(Fragment, null, children)
  }
  return { ...base, LazyMotion: CapturingLazyMotion, m: { div: CapturingDiv } }
})

import PageTransition from "@/components/motion/PageTransition"

const setReduceMotion = (matches: boolean) => {
  const matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }))
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: matchMedia,
  })
  return matchMedia
}

describe("PageTransition", () => {
  beforeEach(() => {
    motionState.initialValues.length = 0
    motionState.props.length = 0
    motionState.lazyFeatures.length = 0
    setReduceMotion(false)
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it("uses the no-initial-animation path on the first non-reduced paint", async () => {
    render(
      <PageTransition>
        <div>Initial paint child</div>
      </PageTransition>
    )
    await expectAnimatedChild("Initial paint child")
    expect(motionState.initialValues).toContain(false)
    expect(motionState.lazyFeatures).toHaveLength(1)
  })

  it("keeps the fallback wrapper when matchMedia is unavailable", () => {
    const originalMatchMedia = window.matchMedia
    try {
      Object.defineProperty(window, "matchMedia", {
        configurable: true,
        value: undefined,
      })
      const { container } = render(
        <PageTransition>
          <div>No media child</div>
        </PageTransition>
      )
      expect(screen.getByText("No media child")).toBeInTheDocument()
      expect(container.querySelector(".bg-page")).toBeInTheDocument()
    } finally {
      Object.defineProperty(window, "matchMedia", {
        configurable: true,
        writable: true,
        value: originalMatchMedia,
      })
    }
  })

  it("renders the reduced-motion fallback wrapper (no framer-motion)", () => {
    setReduceMotion(true)
    const { container } = render(
      <PageTransition>
        <div>Hello reduced</div>
      </PageTransition>
    )
    expect(screen.getByText("Hello reduced")).toBeInTheDocument()
    // simple fallback wrapper carries the bg-page class
    expect(container.querySelector(".bg-page")).toBeInTheDocument()
  })

  it("renders children through the animated framer-motion path", async () => {
    render(
      <PageTransition>
        <div>Hello animated</div>
      </PageTransition>
    )
    // motion module loads asynchronously via useEffect — poll until it commits
    await expectAnimatedChild("Hello animated")
    expect(screen.getByText("Hello animated")).toBeInTheDocument()
  })

  it("keeps children visible after the painted->animated transition", async () => {
    // first render flips the module-level didPaint flag + loads motion module
    const first = render(
      <PageTransition>
        <div>First paint child</div>
      </PageTransition>
    )
    await expectAnimatedChild("First paint child")
    first.unmount()

    // a subsequent independent render now starts with didPaint=true (hasPainted),
    // exercising the `initial = { opacity: 0, ... }` branch instead of `false`
    render(
      <PageTransition>
        <div>Second paint child</div>
      </PageTransition>
    )
    await expectAnimatedChild("Second paint child")
    expect(screen.getByText("Second paint child")).toBeInTheDocument()
    expect(motionState.initialValues.at(-1)).toEqual({
      opacity: 0,
      scale: 0.98,
      y: "0.75rem",
      filter: "blur(0.25rem)",
    })
    expect(motionState.props.at(-1)?.animate).toEqual({
      opacity: 1,
      y: 0,
      scale: 1,
      filter: "blur(0rem)",
      transition: {
        type: "spring",
        stiffness: 200,
        damping: 28,
        mass: 1.2,
        restDelta: 0.001,
      },
    })
    expect(motionState.props.at(-1)?.exit).toEqual({
      opacity: 0,
      scale: 0.99,
      y: -12,
      filter: "blur(0.125rem)",
      transition: expect.objectContaining({
        duration: expect.any(Number),
        ease: expect.anything(),
      }),
    })
  })

  it("responds to a reduced-motion preference change after mount", async () => {
    let changeHandler: ((event: MediaQueryListEvent) => void) | null = null
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: vi.fn((_evt: string, handler: (event: MediaQueryListEvent) => void) => {
          changeHandler = handler
        }),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    })

    render(
      <PageTransition>
        <div>Toggle child</div>
      </PageTransition>
    )
    await expectAnimatedChild("Toggle child")
    // the media-change listener was registered (covers the addEventListener branch)
    expect(changeHandler).toBeTypeOf("function")
    act(() => changeHandler?.({ matches: true } as MediaQueryListEvent))
    expect(screen.getByText("Toggle child").closest(WILL_CHANGE)).toBeNull()
  })

  it("supports the legacy MediaQueryList listener API and cleans it up", async () => {
    let legacyHandler: ((event: MediaQueryListEvent) => void) | null = null
    const removeListener = vi.fn()
    const media = {
      matches: false,
      media: "(prefers-reduced-motion: reduce)",
      onchange: null,
      addEventListener: undefined,
      removeEventListener: undefined,
      addListener: vi.fn((handler: (event: MediaQueryListEvent) => void) => {
        legacyHandler = handler
      }),
      removeListener,
      dispatchEvent: vi.fn(),
    }
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      writable: true,
      value: vi.fn(() => media),
    })

    const view = render(
      <PageTransition>
        <div>Legacy media child</div>
      </PageTransition>
    )
    await waitFor(() => expect(legacyHandler).toBeTypeOf("function"))
    act(() => legacyHandler?.({ matches: true } as MediaQueryListEvent))
    expect(screen.getByText("Legacy media child").closest(WILL_CHANGE)).toBeNull()

    view.unmount()
    expect(removeListener).toHaveBeenCalledOnce()
  })
})
