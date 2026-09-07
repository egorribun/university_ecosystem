import { act, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi, beforeEach } from "vitest"

const { mediaMock, observerState } = vi.hoisted(() => ({
  mediaMock: vi.fn(),
  observerState: {
    callbacks: [] as IntersectionObserverCallback[],
    disconnects: [] as ReturnType<typeof vi.fn>[],
    observes: [] as ReturnType<typeof vi.fn>[],
    options: [] as IntersectionObserverInit[],
  },
}))

const mediaQueries: string[] = []
const translationNamespaces: unknown[] = []

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: (namespaces: unknown) => {
    translationNamespaces.push(namespaces)
    return {
      t: (key: string) => key,
      i18n: { language: "en", changeLanguage: () => Promise.resolve() },
    }
  },
}))
vi.mock("@/hooks/useMediaQuery", () => ({
  default: (query: string) => {
    mediaQueries.push(query)
    return mediaMock()
  },
}))

import { NewsTableOfContents } from "@/components/news/NewsTableOfContents"
import type { TocEntry } from "@/hooks/useArticleHeadings"

const HEADINGS: TocEntry[] = [
  { id: "background", text: "Background", level: 2 },
  { id: "methodology", text: "Methodology", level: 2 },
  { id: "data-pipeline", text: "Data Pipeline", level: 3 },
  { id: "findings", text: "Key Findings", level: 2 },
]

const makeObserverEntry = (target: Element, isIntersecting: boolean): IntersectionObserverEntry => {
  const bounds = target.getBoundingClientRect()
  return {
    boundingClientRect: bounds,
    intersectionRatio: isIntersecting ? 1 : 0,
    intersectionRect: bounds,
    isIntersecting,
    rootBounds: null,
    target,
    time: performance.now(),
  }
}

describe("NewsTableOfContents", () => {
  beforeEach(() => {
    document
      .querySelectorAll("#background, #methodology, #data-pipeline, #findings")
      .forEach((el) => el.remove())
    mediaMock.mockReset()
    mediaMock.mockReturnValue(true) // desktop by default
    mediaQueries.length = 0
    translationNamespaces.length = 0
    observerState.callbacks = []
    observerState.disconnects = []
    observerState.observes = []
    observerState.options = []
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        observe = vi.fn()
        disconnect = vi.fn()

        constructor(callback: IntersectionObserverCallback, options?: IntersectionObserverInit) {
          observerState.callbacks.push(callback)
          observerState.disconnects.push(this.disconnect)
          observerState.observes.push(this.observe)
          observerState.options.push(options ?? {})
        }
      }
    )
  })

  it("renders nothing when there are fewer than 3 headings", () => {
    const { container } = render(<NewsTableOfContents headings={HEADINGS.slice(0, 2)} />)
    expect(container).toBeEmptyDOMElement()
  })

  it("does not create an observer for an empty heading list", () => {
    render(<NewsTableOfContents headings={[]} />)
    expect(observerState.callbacks).toHaveLength(0)
  })

  it("renders the nav, title, count, and all headings on desktop", () => {
    render(<NewsTableOfContents headings={HEADINGS} />)
    expect(translationNamespaces).toContainEqual(["news"])
    expect(mediaQueries).toContain("(min-width: 1024px)")
    expect(screen.getByRole("navigation", { name: "news:toc.label" })).toBeInTheDocument()
    expect(screen.getByText("news:toc.title")).toBeInTheDocument()
    expect(screen.getByText("4")).toBeInTheDocument()
    const header = screen.getByRole("button", { name: /news:toc.title/ })
    expect(header).toBeDisabled()
    expect(header).toHaveAttribute("aria-expanded", "true")
    expect(header).not.toHaveClass("hover:bg-(--bg-surface)/(--opacity-hover)")
    expect(header.querySelector("svg.rotate-180")).not.toBeInTheDocument()
    expect(header).toHaveClass(
      "flex",
      "w-full",
      "items-center",
      "gap-2",
      "px-4",
      "py-3",
      "text-sm",
      "font-bold",
      "transition-colors"
    )
    for (const h of HEADINGS) {
      expect(screen.getByRole("button", { name: h.text })).toBeInTheDocument()
    }
    expect(screen.getByRole("button", { name: "Data Pipeline" })).toHaveClass("pl-6")
    expect(screen.getByRole("button", { name: "Background" })).not.toHaveClass("pl-6")
    expect(screen.getByRole("navigation")).toHaveClass(
      "news-toc",
      "rounded-xl",
      "border",
      "border-glass-border/(--opacity-soft)",
      "overflow-hidden",
      "transition-all",
      "duration-base",
      "glass-layer-surface",
      "glass-noise"
    )
  })

  it("toggles the collapsed link list on mobile", async () => {
    mediaMock.mockReturnValue(false) // mobile → collapsed initially
    const user = userEvent.setup()
    const target = document.createElement("h2")
    target.id = "background"
    target.scrollIntoView = vi.fn()
    document.body.appendChild(target)
    render(<NewsTableOfContents headings={HEADINGS} />)
    const header = screen.getByRole("button", { name: /news:toc.title/ })
    expect(header).toHaveAttribute("aria-expanded", "false")
    expect(header).toBeEnabled()
    expect(header).toHaveClass("hover:bg-(--bg-surface)/(--opacity-hover)")
    expect(screen.queryByRole("button", { name: "Background" })).not.toBeInTheDocument()
    await user.click(screen.getByText("news:toc.title"))
    expect(header).toHaveAttribute("aria-expanded", "true")
    const chevron = header.querySelector("svg.rotate-180")!
    expect(chevron).toHaveClass(
      "h-4",
      "w-4",
      "text-(--text-secondary)",
      "transition-transform",
      "duration-fast",
      "rotate-180"
    )
    expect(screen.getByRole("button", { name: "Background" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Background" })).toHaveClass(
      "w-full",
      "text-left",
      "rounded-lg",
      "px-3",
      "py-1.5",
      "text-sm",
      "leading-snug",
      "transition-colors"
    )
    await user.click(screen.getByRole("button", { name: "Background" }))
    expect(screen.queryByRole("button", { name: "Background" })).not.toBeInTheDocument()
    document.body.removeChild(target)
  })

  it("scrolls to a heading when a link is clicked", async () => {
    const target = document.createElement("h2")
    target.id = "background"
    target.scrollIntoView = vi.fn()
    document.body.appendChild(target)
    const user = userEvent.setup()
    render(<NewsTableOfContents headings={HEADINGS} />)
    await user.click(screen.getByRole("button", { name: "Background" }))
    expect(target.scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" })
    document.body.removeChild(target)
  })

  it("tracks intersecting headings and ignores missing scroll targets", async () => {
    const firstTarget = document.createElement("h2")
    firstTarget.id = "background"
    document.body.appendChild(firstTarget)
    const user = userEvent.setup()
    const { rerender } = render(<NewsTableOfContents headings={HEADINGS} />)

    const observer = observerState.callbacks.length
    expect(observer).toBeGreaterThan(0)

    act(() => {
      observerState.callbacks[0]?.(
        [makeObserverEntry(firstTarget, true)],
        {} as IntersectionObserver
      )
    })
    expect(screen.getByRole("button", { name: "Background" })).toHaveClass("font-semibold")
    expect(screen.getByRole("button", { name: "Methodology" })).not.toHaveClass("font-semibold")

    act(() => {
      observerState.callbacks[0]?.(
        [makeObserverEntry(firstTarget, false)],
        {} as IntersectionObserver
      )
    })
    expect(screen.getByRole("button", { name: "Background" })).toHaveClass("font-semibold")

    await user.click(screen.getByRole("button", { name: "Methodology" }))
    expect(screen.getByRole("button", { name: "Background" })).toHaveClass("font-semibold")
    expect(screen.getByRole("button", { name: "Methodology" })).toHaveClass(
      "text-(--text-secondary)",
      "hover:text-text-primary",
      "hover:bg-(--bg-surface)/(--opacity-hover)"
    )
    rerender(<NewsTableOfContents headings={[...HEADINGS]} />)
    expect(observerState.disconnects[0]).toHaveBeenCalled()
    document.body.removeChild(firstTarget)
  })

  it("observes only mounted headings with the exact observer options", () => {
    const firstTarget = document.createElement("h2")
    firstTarget.id = "background"
    document.body.appendChild(firstTarget)
    render(<NewsTableOfContents headings={HEADINGS} />)
    expect(observerState.callbacks[0]).toBeDefined()
    expect(observerState.options[0]).toEqual({ rootMargin: "-80px 0px -70% 0px", threshold: 0 })
    expect(observerState.observes[0]).toHaveBeenCalledWith(firstTarget)
    expect(observerState.observes[0]).toHaveBeenCalledTimes(1)
    expect(observerState.disconnects[0]).not.toHaveBeenCalled()
    document.body.removeChild(firstTarget)
  })

  it("resets mobile expansion when navigating to a different article", async () => {
    mediaMock.mockReturnValue(false)
    const user = userEvent.setup()
    const { rerender } = render(<NewsTableOfContents headings={HEADINGS} />)
    await user.click(screen.getByText("news:toc.title"))
    expect(screen.getByRole("button", { name: "Background" })).toBeInTheDocument()
    rerender(
      <NewsTableOfContents
        headings={[...HEADINGS, { id: "appendix", text: "Appendix", level: 2 }]}
      />
    )
    expect(screen.queryByRole("button", { name: "Background" })).not.toBeInTheDocument()
  })
})
