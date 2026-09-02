import { fireEvent, render, screen } from "@testing-library/react"
import { beforeAll, describe, expect, it, vi } from "vitest"

import AsyncImage from "../media/AsyncImage"

let lastObserverOptions: IntersectionObserverInit | undefined
let observerConstructed = 0

beforeAll(() => {
  // Mock IntersectionObserver to immediately trigger visibility
  class MockIntersectionObserver implements IntersectionObserver {
    root: Element | Document | null = null
    rootMargin: string = ""
    readonly scrollMargin: string = ""
    thresholds: ReadonlyArray<number> = []
    callback: IntersectionObserverCallback

    constructor(callback: IntersectionObserverCallback, options?: IntersectionObserverInit) {
      this.callback = callback
      lastObserverOptions = options
      observerConstructed += 1
    }

    observe(target: Element): void {
      // Immediately report the element as intersecting
      this.callback(
        [
          {
            isIntersecting: true,
            target,
            boundingClientRect: target.getBoundingClientRect(),
            intersectionRatio: 1,
            intersectionRect: target.getBoundingClientRect(),
            rootBounds: null,
            time: Date.now(),
          },
        ],
        this
      )
    }

    unobserve(): void {}
    disconnect(): void {}
    takeRecords(): IntersectionObserverEntry[] {
      return []
    }
  }

  window.IntersectionObserver = MockIntersectionObserver as typeof IntersectionObserver
})

describe("AsyncImage", () => {
  const src = "https://example.com/image.png"

  it("uses a valid pixel root margin and preserves the default image contract", () => {
    const before = observerConstructed
    render(<AsyncImage src={src} />)

    expect(observerConstructed).toBeGreaterThan(before)
    expect(lastObserverOptions).toEqual({ rootMargin: "200px", threshold: 0, root: null })
    expect(screen.getByTestId("async-image-img")).toHaveAttribute("alt", "")
  })

  it("renders skeleton while loading and hides it after load", () => {
    render(<AsyncImage src={src} alt="test" style={{ width: 200, height: 120 }} />)

    expect(screen.getByTestId("async-image-skeleton")).toBeInTheDocument()

    const image = screen.getByTestId("async-image-img") as HTMLImageElement
    fireEvent.load(image)

    expect(screen.queryByTestId("async-image-skeleton")).not.toBeInTheDocument()
  })

  it("displays fallback on error", () => {
    render(<AsyncImage src={src} alt="error" style={{ width: 200, height: 120 }} />)

    const image = screen.getByTestId("async-image-img") as HTMLImageElement
    fireEvent.error(image)

    expect(screen.getByTestId("async-image-fallback")).toBeInTheDocument()
  })

  it("renders a blurred thumbnail while loading and forwards image callbacks", () => {
    const onLoad = vi.fn()
    const onError = vi.fn()
    render(
      <AsyncImage
        src={src}
        thumbSrc="https://example.com/thumb.png"
        alt="with callbacks"
        onLoad={onLoad}
        onError={onError}
      />
    )

    expect(document.querySelector('img[src="https://example.com/thumb.png"]')).toHaveAttribute(
      "aria-hidden",
      "true"
    )

    const image = screen.getByTestId("async-image-img") as HTMLImageElement
    fireEvent.load(image)
    expect(onLoad).toHaveBeenCalledOnce()
    expect(
      document.querySelector('img[src="https://example.com/thumb.png"]')
    ).not.toBeInTheDocument()

    fireEvent.error(image)
    expect(onError).toHaveBeenCalledOnce()
  })

  it("handles load and error transitions without optional callbacks", () => {
    render(<AsyncImage src={src} alt="without callbacks" />)
    const image = screen.getByTestId("async-image-img") as HTMLImageElement

    fireEvent.load(image)
    expect(screen.queryByTestId("async-image-skeleton")).not.toBeInTheDocument()
    fireEvent.error(image)
    expect(screen.getByTestId("async-image-fallback")).toBeInTheDocument()
  })

  it("renders a fallback source when the primary source is absent", () => {
    const { rerender } = render(<AsyncImage fallbackSrc="/fallback.png" alt="fallback source" />)

    const fallbackImage = screen.getByAltText("fallback source") as HTMLImageElement
    expect(fallbackImage).toHaveAttribute("src", "/fallback.png")
    expect(screen.queryByTestId("async-image-fallback")).not.toBeInTheDocument()

    rerender(<AsyncImage fallbackSrc="/fallback.png" />)
    expect(document.querySelector('img[src="/fallback.png"]')).toHaveAttribute(
      "aria-hidden",
      "true"
    )
  })

  it("renders a custom fallback when no image source is available", () => {
    render(<AsyncImage fallback={<span>Custom fallback</span>} />)

    expect(screen.getByText("Custom fallback")).toBeInTheDocument()
    expect(screen.getByTestId("async-image-fallback")).toBeInTheDocument()
  })

  it("renders the default fallback when both image sources are absent", () => {
    render(<AsyncImage />)

    expect(screen.getByTestId("async-image-fallback")).toBeInTheDocument()
  })

  it("forces reload when version changes", () => {
    const { rerender } = render(
      <AsyncImage src={src} version={1} alt="version" style={{ width: 120, height: 120 }} />
    )

    const image = screen.getByTestId("async-image-img") as HTMLImageElement
    fireEvent.load(image)

    expect(screen.queryByTestId("async-image-skeleton")).not.toBeInTheDocument()

    rerender(<AsyncImage src={src} version={2} alt="version" style={{ width: 120, height: 120 }} />)

    expect(screen.getByTestId("async-image-skeleton")).toBeInTheDocument()
  })
})
