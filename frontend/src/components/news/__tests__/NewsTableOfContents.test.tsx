import { act, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi, beforeEach } from "vitest"

const { mediaMock, observerState } = vi.hoisted(() => ({
  mediaMock: vi.fn(),
  observerState: {
    callbacks: [] as IntersectionObserverCallback[],
    disconnects: [] as ReturnType<typeof vi.fn>[],
  },
}))

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))
vi.mock("@/hooks/useMediaQuery", () => ({ default: () => mediaMock() }))

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
    mediaMock.mockReset()
    mediaMock.mockReturnValue(true) // desktop by default
    observerState.callbacks = []
    observerState.disconnects = []
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        observe = vi.fn()
        disconnect = vi.fn()

        constructor(callback: IntersectionObserverCallback) {
          observerState.callbacks.push(callback)
          observerState.disconnects.push(this.disconnect)
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
    expect(screen.getByRole("navigation", { name: "news:toc.label" })).toBeInTheDocument()
    expect(screen.getByText("news:toc.title")).toBeInTheDocument()
    expect(screen.getByText("4")).toBeInTheDocument()
    for (const h of HEADINGS) {
      expect(screen.getByRole("button", { name: h.text })).toBeInTheDocument()
    }
  })

  it("toggles the collapsed link list on mobile", async () => {
    mediaMock.mockReturnValue(false) // mobile → collapsed initially
    const user = userEvent.setup()
    const target = document.createElement("h2")
    target.id = "background"
    target.scrollIntoView = vi.fn()
    document.body.appendChild(target)
    render(<NewsTableOfContents headings={HEADINGS} />)
    expect(screen.queryByRole("button", { name: "Background" })).not.toBeInTheDocument()
    await user.click(screen.getByText("news:toc.title"))
    expect(screen.getByRole("button", { name: "Background" })).toBeInTheDocument()
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
    expect(target.scrollIntoView).toHaveBeenCalled()
    document.body.removeChild(target)
  })

  it("tracks intersecting headings and ignores missing scroll targets", async () => {
    const firstTarget = document.createElement("h2")
    firstTarget.id = "background"
    document.body.appendChild(firstTarget)
    const user = userEvent.setup()
    const { rerender } = render(<NewsTableOfContents headings={HEADINGS} />)

    act(() => {
      observerState.callbacks[0]?.(
        [makeObserverEntry(firstTarget, false), makeObserverEntry(firstTarget, true)],
        {} as IntersectionObserver
      )
    })
    expect(screen.getByRole("button", { name: "Background" })).toHaveClass("font-semibold")

    await user.click(screen.getByRole("button", { name: "Methodology" }))
    rerender(<NewsTableOfContents headings={[...HEADINGS]} />)
    expect(observerState.disconnects[0]).toHaveBeenCalled()
    document.body.removeChild(firstTarget)
  })
})
