import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi, beforeEach } from "vitest"

const { mediaMock } = vi.hoisted(() => ({ mediaMock: vi.fn() }))

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

describe("NewsTableOfContents", () => {
  beforeEach(() => {
    mediaMock.mockReset()
    mediaMock.mockReturnValue(true) // desktop by default
  })

  it("renders nothing when there are fewer than 3 headings", () => {
    const { container } = render(<NewsTableOfContents headings={HEADINGS.slice(0, 2)} />)
    expect(container).toBeEmptyDOMElement()
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
    render(<NewsTableOfContents headings={HEADINGS} />)
    expect(screen.queryByRole("button", { name: "Background" })).not.toBeInTheDocument()
    await user.click(screen.getByText("news:toc.title"))
    expect(screen.getByRole("button", { name: "Background" })).toBeInTheDocument()
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
})
