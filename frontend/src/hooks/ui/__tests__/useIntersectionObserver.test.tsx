import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { act, cleanup, render, screen } from "@testing-library/react"
import { useIntersectionObserver } from "../useIntersectionObserver"

// This double controls observation delivery and cleanup. It does not implement
// browser geometry or validate/normalize rootMargin strings.
class TestIntersectionObserver {
  static instances: TestIntersectionObserver[] = []
  readonly targets = new Set<Element>()
  readonly observe = vi.fn((target: Element) => this.targets.add(target))
  readonly disconnect = vi.fn(() => this.targets.clear())

  constructor(
    private readonly callback: IntersectionObserverCallback,
    readonly options?: IntersectionObserverInit
  ) {
    TestIntersectionObserver.instances.push(this)
  }

  emit(isIntersecting: boolean) {
    const entries = [...this.targets].map((target) => ({
      target,
      time: 0,
      isIntersecting,
      intersectionRatio: isIntersecting ? 1 : 0,
      boundingClientRect: target.getBoundingClientRect(),
      intersectionRect: target.getBoundingClientRect(),
      rootBounds: null,
    }))
    if (entries.length > 0) {
      this.callback(entries, this as unknown as IntersectionObserver)
    }
  }
}

type ObserverOptions = Parameters<typeof useIntersectionObserver>[0]

function Probe({ options }: { options: ObserverOptions }) {
  const [ref, isVisible] = useIntersectionObserver(options)
  return <div ref={ref} data-testid="probe" data-visible={String(isVisible)} />
}

function activeObserver() {
  const active = TestIntersectionObserver.instances.filter((observer) => observer.targets.size > 0)
  expect(active).toHaveLength(1)
  const observer = active[0]
  if (!observer) throw new Error("expected one active IntersectionObserver")
  return observer
}

describe("useIntersectionObserver", () => {
  let descriptors: { target: typeof globalThis | Window; descriptor?: PropertyDescriptor }[]

  beforeEach(() => {
    TestIntersectionObserver.instances = []
    descriptors = [window, globalThis].map((target) => ({
      target,
      descriptor: Object.getOwnPropertyDescriptor(target, "IntersectionObserver"),
    }))
    vi.stubGlobal("IntersectionObserver", TestIntersectionObserver)
  })

  afterEach(() => {
    const errors: unknown[] = []
    const steps = [
      cleanup,
      () => vi.unstubAllGlobals(),
      ...descriptors.map(({ target, descriptor }) => () => {
        if (descriptor) Object.defineProperty(target, "IntersectionObserver", descriptor)
        else if (!Reflect.deleteProperty(target, "IntersectionObserver")) {
          throw new Error("Failed to restore IntersectionObserver descriptor")
        }
      }),
    ]
    for (const step of steps) {
      try {
        step()
      } catch (error) {
        errors.push(error)
      }
    }
    if (errors.length)
      throw new AggregateError(errors, "useIntersectionObserver fixture cleanup failed")
  })

  it.each([
    { name: "omitted option properties", options: {} },
    {
      name: "undefined option properties",
      options: {
        threshold: undefined,
        root: undefined,
        rootMargin: undefined,
        freezeOnceVisible: undefined,
      },
    },
  ])("continues reporting visibility changes with $name", ({ options }) => {
    const { unmount } = render(<Probe options={options} />)
    const target = screen.getByTestId("probe")
    expect(activeObserver().observe).toHaveBeenCalledExactlyOnceWith(target)
    expect(activeObserver().options).toMatchObject({ threshold: 0, root: null })
    expect(target).toHaveAttribute("data-visible", "false")

    // Repeated real callback transitions distinguish ongoing observation from
    // the explicit freeze-on-first-visibility option.
    for (const visible of [true, false, true, false]) {
      act(() => activeObserver().emit(visible))
      expect(target).toHaveAttribute("data-visible", String(visible))
      expect(activeObserver().targets.has(target)).toBe(true)
    }

    unmount()
    expect(
      TestIntersectionObserver.instances.every((observer) => observer.targets.size === 0)
    ).toBe(true)
    for (const observer of TestIntersectionObserver.instances) {
      expect(observer.disconnect).toHaveBeenCalledTimes(1)
    }
  })

  it("observes the node with supplied options and freezes after first visibility", () => {
    render(<Probe options={{ threshold: 0.5, rootMargin: "12px", freezeOnceVisible: true }} />)
    const observer = activeObserver()
    expect(observer.observe).toHaveBeenCalledExactlyOnceWith(screen.getByTestId("probe"))
    expect(observer.options).toEqual({ threshold: 0.5, root: null, rootMargin: "12px" })
    expect(screen.getByTestId("probe")).toHaveAttribute("data-visible", "false")

    act(() => observer.emit(true))
    expect(screen.getByTestId("probe")).toHaveAttribute("data-visible", "true")
    expect(observer.disconnect).toHaveBeenCalledTimes(1)
    expect(observer.targets.size).toBe(0)
    act(() => observer.emit(false))
    expect(screen.getByTestId("probe")).toHaveAttribute("data-visible", "true")
  })

  it("disconnects the previous observation when caller options change", () => {
    const { rerender, unmount } = render(<Probe options={{ threshold: 0.25 }} />)
    const previous = activeObserver()
    rerender(<Probe options={{ threshold: 0.75, rootMargin: "24px", freezeOnceVisible: false }} />)
    expect(previous.disconnect).toHaveBeenCalledTimes(1)
    const replacement = activeObserver()
    expect(replacement).not.toBe(previous)
    expect(replacement.options).toEqual({ threshold: 0.75, root: null, rootMargin: "24px" })
    act(() => replacement.emit(true))
    expect(screen.getByTestId("probe")).toHaveAttribute("data-visible", "true")
    unmount()
    for (const observer of TestIntersectionObserver.instances) {
      expect(observer.disconnect).toHaveBeenCalledTimes(1)
    }
  })

  it("returns a false visibility state without creating an observer when unsupported", () => {
    vi.stubGlobal("IntersectionObserver", undefined)
    render(<Probe options={{}} />)
    expect(screen.getByTestId("probe")).toHaveAttribute("data-visible", "false")
    expect(TestIntersectionObserver.instances).toHaveLength(0)
  })
})
