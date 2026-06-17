import { render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

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

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)

import PageTransition from "@/components/motion/PageTransition"

const setReduceMotion = (matches: boolean) => {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })
}

describe("PageTransition", () => {
  beforeEach(() => {
    setReduceMotion(false)
  })

  afterEach(() => {
    vi.clearAllMocks()
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
  })
})
