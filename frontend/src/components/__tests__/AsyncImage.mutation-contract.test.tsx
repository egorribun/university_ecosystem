import type { ReactNode } from "react"
import { fireEvent, render, screen } from "@testing-library/react"
import { renderToString } from "react-dom/server"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

/**
 * AsyncImage keeps a small but important state machine around a lazily-mounted
 * image.  This suite keeps the framer-motion props observable so a mutation of
 * the status transitions cannot hide behind the same DOM skeleton/fallback.
 */
const state = vi.hoisted(() => ({
  visible: true,
  observerOptions: undefined as Record<string, unknown> | undefined,
  resolvedSources: [] as unknown[][],
  versionParams: [] as unknown[][],
}))

vi.mock("framer-motion", async () => {
  const React = await import("react")
  type Props = Record<string, unknown> & { children?: ReactNode }
  const motionOnly = new Set(["initial", "animate", "exit", "transition"])
  const serialise = (value: unknown) => (value === undefined ? "undefined" : JSON.stringify(value))
  const Motion = React.forwardRef<HTMLElement, Props>(function Motion({ children, ...props }, ref) {
    const tag = (props["data-motion-tag"] as string | undefined) ?? "div"
    const cleaned: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(props)) {
      if (key === "data-motion-tag" || motionOnly.has(key)) continue
      cleaned[key] = value
    }
    return React.createElement(
      tag,
      {
        ...cleaned,
        ref,
        "data-motion-initial": serialise(props.initial),
        "data-motion-animate": serialise(props.animate),
        "data-motion-transition": serialise(props.transition),
      },
      children as ReactNode
    )
  })
  const components = new Map<string, unknown>()
  const motion = new Proxy(
    {},
    {
      get: (_target, key) => {
        if (typeof key !== "string") return undefined
        const cached = components.get(key)
        if (cached) return cached
        const component = React.forwardRef<HTMLElement, Props>(function MotionElement(props, ref) {
          return React.createElement(Motion, { ...props, ref, "data-motion-tag": key })
        })
        components.set(key, component)
        return component
      },
    }
  )
  return {
    m: motion,
    motion,
    AnimatePresence: ({ children }: { children?: ReactNode }) => <>{children}</>,
  }
})

vi.mock("@/hooks/useIntersectionObserver", () => ({
  useIntersectionObserver: (_ref: unknown, options: Record<string, unknown>) => {
    state.observerOptions = options
    return state.visible ? { isIntersecting: true } : { isIntersecting: false }
  },
}))

vi.mock("@/utils/media", async () => {
  const actual = await vi.importActual<typeof import("@/utils/media")>("@/utils/media")
  return {
    ...actual,
    resolveProxyImageUrl: (...args: Parameters<typeof actual.resolveProxyImageUrl>) => {
      state.resolvedSources.push(args)
      return actual.resolveProxyImageUrl(...args)
    },
    addVersionParam: (...args: Parameters<typeof actual.addVersionParam>) => {
      state.versionParams.push(args)
      return actual.addVersionParam(...args)
    },
  }
})

vi.mock("@/components/settings", () => ({
  Skeleton: ({ width, height }: { width?: string; height?: string }) => (
    <div data-testid="skeleton" style={{ width, height }} />
  ),
}))

import AsyncImage, {
  getAsyncImageInitialStatus,
  getAsyncImageResolvedStatus,
} from "../media/AsyncImage"

const primary = "https://example.com/image.png"

beforeEach(() => {
  state.visible = true
  state.observerOptions = undefined
  state.resolvedSources.length = 0
  state.versionParams.length = 0
})

afterEach(() => vi.restoreAllMocks())

describe("AsyncImage mutation contracts", () => {
  it("keeps source status transitions explicit for SSR and client effects", () => {
    expect(getAsyncImageInitialStatus(primary)).toBe("loading")
    expect(getAsyncImageInitialStatus()).toBe("idle")
    expect(getAsyncImageResolvedStatus(primary)).toBe("loading")
    expect(getAsyncImageResolvedStatus("")).toBe("idle")
  })

  it("exposes the component identity for diagnostics", () => {
    expect(AsyncImage.displayName).toBe("AsyncImage")
  })
  it("passes a pixel root margin and freezes the observer after visibility", () => {
    render(<AsyncImage src={primary} />)

    expect(state.observerOptions).toEqual({
      rootMargin: "200px",
      freezeOnceVisible: true,
    })
  })

  it("keeps the default and explicit object-fit values on primary, thumb and fallback images", () => {
    const { rerender } = render(<AsyncImage src={primary} />)
    expect(screen.getByTestId("async-image-img")).toHaveStyle({ objectFit: "cover" })
    expect(screen.getByTestId("async-image-img").parentElement).toHaveClass(
      "relative",
      "overflow-hidden",
      "rounded-lg"
    )
    expect(state.versionParams).toHaveLength(0)

    rerender(<AsyncImage src={primary} thumbSrc="/thumb.png" objectFit="contain" />)
    expect(screen.getByTestId("async-image-img")).toHaveStyle({ objectFit: "contain" })
    expect(document.querySelector('img[src="/thumb.png"]')).toHaveStyle({ objectFit: "contain" })

    rerender(<AsyncImage fallbackSrc="/fallback.png" objectFit="scale-down" />)
    expect(document.querySelector('img[src="/fallback.png"]')).toHaveStyle({
      objectFit: "scale-down",
    })
  })

  it("does not mount fallbackSrc while a primary source is available", () => {
    render(<AsyncImage src={primary} fallbackSrc="/fallback.png" />)

    expect(screen.getByTestId("async-image-img")).toHaveAttribute("src", primary)
    expect(document.querySelector('img[src="/fallback.png"]')).not.toBeInTheDocument()
  })

  it("exposes loading and loaded animation states instead of only hiding the skeleton", () => {
    render(<AsyncImage src={primary} />)
    const image = screen.getByTestId("async-image-img")
    expect(image).toHaveAttribute("data-motion-animate", JSON.stringify({ opacity: 0 }))
    expect(image).toHaveAttribute("data-motion-transition", JSON.stringify({ duration: 0.3 }))
    expect(screen.getByTestId("async-image-skeleton")).toBeInTheDocument()

    fireEvent.load(image)

    expect(screen.queryByTestId("async-image-skeleton")).not.toBeInTheDocument()
    expect(screen.getByTestId("async-image-img")).toHaveAttribute(
      "data-motion-animate",
      JSON.stringify({ opacity: 1 })
    )
  })

  it("exposes an error state and renders a supplied fallback after a failed load", () => {
    render(<AsyncImage src={primary} fallback={<span>Custom fallback</span>} />)
    const image = screen.getByTestId("async-image-img")

    expect(screen.queryByText("Custom fallback")).not.toBeInTheDocument()
    fireEvent.error(image)

    expect(screen.getByTestId("async-image-fallback")).toHaveTextContent("Custom fallback")
    expect(screen.getByTestId("async-image-img")).toHaveAttribute(
      "data-motion-animate",
      JSON.stringify({ opacity: 0 })
    )
  })

  it("uses the canonical fallback state for source-less custom and default fallbacks", () => {
    const { rerender } = render(<AsyncImage fallback={<span>Custom fallback</span>} />)
    expect(screen.getByTestId("async-image-fallback")).toHaveTextContent("Custom fallback")

    rerender(<AsyncImage />)
    expect(screen.getByTestId("async-image-fallback")).toBeInTheDocument()
    expect(screen.getByTestId("async-image-fallback")).not.toHaveTextContent("Custom fallback")
  })

  it("does not mount the primary image before intersection and mounts it after visibility", () => {
    state.visible = false
    const { rerender } = render(<AsyncImage src={primary} />)

    expect(screen.queryByTestId("async-image-img")).not.toBeInTheDocument()
    expect(screen.getByTestId("async-image-skeleton")).toBeInTheDocument()

    state.visible = true
    rerender(<AsyncImage src={primary} />)
    expect(screen.getByTestId("async-image-img")).toBeInTheDocument()
  })

  it("resolves and rotates the version query parameter while preserving the loading transition", () => {
    const { rerender } = render(<AsyncImage src={primary} version={1} />)
    expect(screen.getByTestId("async-image-img")).toHaveAttribute(
      "src",
      "https://example.com/image.png?_v=1"
    )
    fireEvent.load(screen.getByTestId("async-image-img"))
    expect(screen.getByTestId("async-image-img")).toHaveAttribute(
      "data-motion-animate",
      JSON.stringify({ opacity: 1 })
    )

    rerender(<AsyncImage src={primary} version={2} />)
    expect(screen.getByTestId("async-image-img")).toHaveAttribute(
      "src",
      "https://example.com/image.png?_v=2"
    )
    expect(screen.getByTestId("async-image-skeleton")).toBeInTheDocument()
    expect(screen.getByTestId("async-image-img")).toHaveAttribute(
      "data-motion-animate",
      JSON.stringify({ opacity: 0 })
    )
    expect(state.versionParams).toEqual([
      [primary, 1],
      [primary, 2],
    ])
  })

  it("uses a fallback source without entering primary loading state when src is absent", () => {
    render(<AsyncImage fallbackSrc="/fallback.png" alt="fallback" />)

    expect(screen.queryByTestId("async-image-skeleton")).not.toBeInTheDocument()
    expect(screen.queryByTestId("async-image-img")).not.toBeInTheDocument()
    expect(screen.getByRole("img", { name: "fallback" })).toHaveAttribute("src", "/fallback.png")
    expect(state.resolvedSources).toHaveLength(0)
    expect(state.versionParams).toHaveLength(0)
  })

  it("keeps the initial loading state observable during SSR before effects run", () => {
    const withSource = renderToString(<AsyncImage src={primary} />)
    expect(withSource).toContain("async-image-skeleton")
    expect(withSource).toContain('src="https://example.com/image.png"')

    const withoutSource = renderToString(<AsyncImage fallbackSrc="/fallback.png" alt="fallback" />)
    expect(withoutSource).not.toContain("async-image-skeleton")
    expect(withoutSource).toContain('src="/fallback.png"')
  })

  it("resets loaded status when the primary source is removed and never prefers fallbackSrc over it", () => {
    const { rerender } = render(
      <AsyncImage src={primary} fallbackSrc="/fallback.png" alt="primary" />
    )
    const image = screen.getByTestId("async-image-img")
    fireEvent.load(image)
    expect(screen.getByTestId("async-image-img")).toHaveAttribute(
      "data-motion-animate",
      JSON.stringify({ opacity: 1 })
    )

    fireEvent.error(screen.getByTestId("async-image-img"))
    expect(screen.queryByRole("img", { name: "fallback" })).not.toBeInTheDocument()

    rerender(<AsyncImage fallbackSrc="/fallback.png" alt="fallback" />)
    expect(screen.getByRole("img", { name: "fallback" })).toHaveAttribute("src", "/fallback.png")
    expect(screen.queryByTestId("async-image-skeleton")).not.toBeInTheDocument()
  })
})
