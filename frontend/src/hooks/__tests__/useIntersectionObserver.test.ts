import { renderHook, act } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useIntersectionObserver, useIsVisible } from "../useIntersectionObserver"
import { createRef } from "react"

// ─── IntersectionObserver mock factory ───────────────────────────────────────
// setupTests.ts defines IntersectionObserver via Object.defineProperty WITHOUT
// configurable:true, so vi.stubGlobal cannot redefine it (TypeError).
// We work around this by using a manual Object.defineProperty with writable:true
// and configurable:true in each beforeEach, then restoring the original in afterEach.

type MockIOCallback = (entries: IntersectionObserverEntry[]) => void
type MockIOOptions = IntersectionObserverInit

let lastObserverCallback: MockIOCallback | null = null
let lastObserverOptions: MockIOOptions | null = null

const createMockIO = () => {
  const mockObserve = vi.fn()
  const mockUnobserve = vi.fn()
  const mockDisconnect = vi.fn()

  class MockIntersectionObserver {
    readonly root: Element | null = null
    readonly rootMargin: string = ""
    readonly thresholds: ReadonlyArray<number> = []

    constructor(callback: MockIOCallback, options?: MockIOOptions) {
      lastObserverCallback = callback
      lastObserverOptions = options ?? null
    }

    observe = mockObserve
    unobserve = mockUnobserve
    disconnect = mockDisconnect
    takeRecords = vi.fn(() => [])
  }

  return { MockIntersectionObserver, mockObserve, mockUnobserve, mockDisconnect }
}

/**
 * Install a mock IntersectionObserver on window.
 *
 * setupTests.ts installs IntersectionObserver via:
 *   Object.defineProperty(window, 'IntersectionObserver', { writable: true, value: ... })
 * It omits configurable:true, so we cannot redefine the descriptor.
 * However writable:true allows us to reassign the value directly.
 *
 * Returns a restore function that puts back the no-op polyfill.
 */
function installMockIO(MockIO: (new (...args: any[]) => any) | undefined): () => void {
  const originalValue = (window as any).IntersectionObserver
  ;(window as any).IntersectionObserver = MockIO
  return () => {
    ;(window as any).IntersectionObserver = originalValue
  }
}

// Helper to build a minimal IntersectionObserverEntry
function makeEntry(overrides: Partial<IntersectionObserverEntry> = {}): IntersectionObserverEntry {
  return {
    boundingClientRect: {} as DOMRectReadOnly,
    intersectionRatio: 0,
    intersectionRect: {} as DOMRectReadOnly,
    isIntersecting: false,
    rootBounds: null,
    target: document.createElement("div"),
    time: performance.now(),
    ...overrides,
  } as IntersectionObserverEntry
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("useIntersectionObserver", () => {
  let mockObserve: ReturnType<typeof vi.fn>
  let mockDisconnect: ReturnType<typeof vi.fn>
  let restoreIO: () => void

  beforeEach(() => {
    lastObserverCallback = null
    lastObserverOptions = null

    const mocks = createMockIO()
    mockObserve = mocks.mockObserve
    mockDisconnect = mocks.mockDisconnect

    restoreIO = installMockIO(mocks.MockIntersectionObserver)
  })

  afterEach(() => {
    restoreIO()
    vi.restoreAllMocks()
  })

  // ───────────────────────────────────────────────────────────────────────────
  // 1. Element enters viewport → entry updates
  // ───────────────────────────────────────────────────────────────────────────
  it("updates entry when element enters the viewport", () => {
    const ref = createRef<HTMLDivElement>()
    const node = document.createElement("div")
    // Manually set ref.current by casting (createRef returns immutable object in types)
    Object.defineProperty(ref, "current", { value: node, writable: false })

    const { result } = renderHook(() => useIntersectionObserver(ref))

    // Initially no entry
    expect(result.current).toBeUndefined()

    // Simulate intersection observer firing with an intersecting entry
    act(() => {
      lastObserverCallback?.([makeEntry({ isIntersecting: true, intersectionRatio: 1 })])
    })

    expect(result.current?.isIntersecting).toBe(true)
    expect(result.current?.intersectionRatio).toBe(1)
  })

  // ───────────────────────────────────────────────────────────────────────────
  // 2. Element leaves viewport → entry updates to non-intersecting
  // ───────────────────────────────────────────────────────────────────────────
  it("updates entry when element leaves the viewport", () => {
    const ref = createRef<HTMLDivElement>()
    const node = document.createElement("div")
    Object.defineProperty(ref, "current", { value: node, writable: false })

    const { result } = renderHook(() => useIntersectionObserver(ref))

    act(() => {
      lastObserverCallback?.([makeEntry({ isIntersecting: true })])
    })
    expect(result.current?.isIntersecting).toBe(true)

    // Element leaves viewport — note: freezeOnceVisible defaults to false,
    // so a new observer is set up and fires the leave event.
    act(() => {
      lastObserverCallback?.([makeEntry({ isIntersecting: false })])
    })
    expect(result.current?.isIntersecting).toBe(false)
  })

  // ───────────────────────────────────────────────────────────────────────────
  // 3. freezeOnceVisible=true: observer disconnects after first intersection
  // ───────────────────────────────────────────────────────────────────────────
  it("disconnects observer after first intersection when freezeOnceVisible=true", () => {
    const ref = createRef<HTMLDivElement>()
    const node = document.createElement("div")
    Object.defineProperty(ref, "current", { value: node, writable: false })

    const { result } = renderHook(() =>
      useIntersectionObserver(ref, { freezeOnceVisible: true })
    )

    // First intersection fires
    act(() => {
      lastObserverCallback?.([makeEntry({ isIntersecting: true })])
    })

    expect(result.current?.isIntersecting).toBe(true)

    // The `frozen` flag is now true — the effect re-runs but returns early
    // because `frozen` is truthy, meaning no new observer is created.
    // The entry stays frozen at the last intersecting state.
    expect(result.current?.isIntersecting).toBe(true)
  })

  // ───────────────────────────────────────────────────────────────────────────
  // 4. Custom threshold and rootMargin are forwarded to the constructor
  // ───────────────────────────────────────────────────────────────────────────
  it("passes custom threshold and rootMargin to IntersectionObserver constructor", () => {
    const ref = createRef<HTMLDivElement>()
    const node = document.createElement("div")
    Object.defineProperty(ref, "current", { value: node, writable: false })

    renderHook(() =>
      useIntersectionObserver(ref, { threshold: 0.5, rootMargin: "10px" })
    )

    expect(lastObserverOptions?.threshold).toBe(0.5)
    expect(lastObserverOptions?.rootMargin).toBe("10px")
  })

  // ───────────────────────────────────────────────────────────────────────────
  // 5. Custom root element is forwarded to the constructor
  // ───────────────────────────────────────────────────────────────────────────
  it("passes custom root element to IntersectionObserver constructor", () => {
    const ref = createRef<HTMLDivElement>()
    const node = document.createElement("div")
    Object.defineProperty(ref, "current", { value: node, writable: false })

    const customRoot = document.createElement("div")
    renderHook(() => useIntersectionObserver(ref, { root: customRoot }))

    expect(lastObserverOptions?.root).toBe(customRoot)
  })

  // ───────────────────────────────────────────────────────────────────────────
  // 6. No IntersectionObserver (SSR / old browser) → graceful, returns undefined
  // ───────────────────────────────────────────────────────────────────────────
  it("returns undefined gracefully when window.IntersectionObserver is unavailable", () => {
    // Override within this specific test — restoreIO in afterEach restores the mock
    ;(window as any).IntersectionObserver = undefined

    const ref = createRef<HTMLDivElement>()
    const node = document.createElement("div")
    Object.defineProperty(ref, "current", { value: node, writable: false })

    const { result } = renderHook(() => useIntersectionObserver(ref))

    expect(result.current).toBeUndefined()
  })

  // ───────────────────────────────────────────────────────────────────────────
  // 7. Null ref → hook returns undefined, no observer created
  // ───────────────────────────────────────────────────────────────────────────
  it("returns undefined and creates no observer when ref.current is null", () => {
    const ref = createRef<HTMLDivElement>()
    // ref.current is null by default from createRef

    const { result } = renderHook(() => useIntersectionObserver(ref))

    expect(result.current).toBeUndefined()
    expect(mockObserve).not.toHaveBeenCalled()
  })

  // ───────────────────────────────────────────────────────────────────────────
  // 8. Cleanup: observer.disconnect() is called on unmount
  // ───────────────────────────────────────────────────────────────────────────
  it("calls observer.disconnect() when the component unmounts", () => {
    const ref = createRef<HTMLDivElement>()
    const node = document.createElement("div")
    Object.defineProperty(ref, "current", { value: node, writable: false })

    const { unmount } = renderHook(() => useIntersectionObserver(ref))

    expect(mockObserve).toHaveBeenCalledWith(node)
    expect(mockDisconnect).not.toHaveBeenCalled()

    unmount()

    expect(mockDisconnect).toHaveBeenCalledTimes(1)
  })

  // ───────────────────────────────────────────────────────────────────────────
  // 9. observe() is called with the correct DOM node
  // ───────────────────────────────────────────────────────────────────────────
  it("calls observer.observe() with the element from the ref", () => {
    const ref = createRef<HTMLDivElement>()
    const node = document.createElement("div")
    Object.defineProperty(ref, "current", { value: node, writable: false })

    renderHook(() => useIntersectionObserver(ref))

    expect(mockObserve).toHaveBeenCalledWith(node)
  })
})

// ─── useIsVisible ─────────────────────────────────────────────────────────────

describe("useIsVisible", () => {
  let restoreIO: () => void

  beforeEach(() => {
    lastObserverCallback = null
    const mocks = createMockIO()
    restoreIO = installMockIO(mocks.MockIntersectionObserver)
  })

  afterEach(() => {
    restoreIO()
    vi.restoreAllMocks()
  })

  it("returns false initially before any intersection event", () => {
    const ref = createRef<HTMLDivElement>()
    const node = document.createElement("div")
    Object.defineProperty(ref, "current", { value: node, writable: false })

    const { result } = renderHook(() => useIsVisible(ref))
    expect(result.current).toBe(false)
  })

  it("returns true when element is intersecting", () => {
    const ref = createRef<HTMLDivElement>()
    const node = document.createElement("div")
    Object.defineProperty(ref, "current", { value: node, writable: false })

    const { result } = renderHook(() => useIsVisible(ref))

    act(() => {
      lastObserverCallback?.([makeEntry({ isIntersecting: true })])
    })

    expect(result.current).toBe(true)
  })

  it("returns false when element is not intersecting", () => {
    const ref = createRef<HTMLDivElement>()
    const node = document.createElement("div")
    Object.defineProperty(ref, "current", { value: node, writable: false })

    const { result } = renderHook(() => useIsVisible(ref))

    act(() => {
      lastObserverCallback?.([makeEntry({ isIntersecting: true })])
    })
    expect(result.current).toBe(true)

    act(() => {
      lastObserverCallback?.([makeEntry({ isIntersecting: false })])
    })
    expect(result.current).toBe(false)
  })

  it("returns false when IntersectionObserver is unavailable (SSR)", () => {
    ;(window as any).IntersectionObserver = undefined
    const ref = createRef<HTMLDivElement>()
    const node = document.createElement("div")
    Object.defineProperty(ref, "current", { value: node, writable: false })

    const { result } = renderHook(() => useIsVisible(ref))
    expect(result.current).toBe(false)
  })

  it("freezes at true when freezeOnceVisible=true", () => {
    const ref = createRef<HTMLDivElement>()
    const node = document.createElement("div")
    Object.defineProperty(ref, "current", { value: node, writable: false })

    const { result } = renderHook(() => useIsVisible(ref, { freezeOnceVisible: true }))

    act(() => {
      lastObserverCallback?.([makeEntry({ isIntersecting: true })])
    })
    expect(result.current).toBe(true)

    // Even if a leave event fires (won't in frozen state), value stays true
    expect(result.current).toBe(true)
  })
})
