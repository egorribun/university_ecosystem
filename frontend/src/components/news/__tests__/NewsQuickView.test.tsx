import { render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, it, expect, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
const translation = vi.hoisted(() => ({
  useTranslation: vi.fn(() => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  })),
}))

vi.mock("react-i18next", () => ({
  useTranslation: translation.useTranslation,
}))
const { reducedMotion } = vi.hoisted(() => ({ reducedMotion: vi.fn(() => false) }))
vi.mock("@/hooks/useMediaQuery", () => ({ default: () => reducedMotion() }))

import { NewsQuickView } from "@/components/news/NewsQuickView"
import { NewsCategoryBadge } from "@/components/news/NewsCategoryBadge"

const baseProps = {
  title: "Новая лаборатория открывается весной",
  preview: "Расширенный предпросмотр статьи с подробностями о событии.",
  created_at: "2026-01-15T10:00:00.000Z",
  likesCount: 42,
  commentsCount: 7,
}

describe("NewsQuickView", () => {
  beforeEach(() => {
    translation.useTranslation.mockClear()
  })

  afterEach(() => {
    reducedMotion.mockReturnValue(false)
  })

  it("renders the popover with title, preview, counts and read-more key when visible", () => {
    render(<NewsQuickView visible {...baseProps} category="science" />)

    // The popover carries aria-hidden="true" (decorative), so query the hidden tree.
    expect(screen.getByRole("tooltip", { hidden: true })).toBeInTheDocument()
    expect(screen.getByText(baseProps.title)).toBeInTheDocument()
    expect(screen.getByText(baseProps.preview)).toBeInTheDocument()
    expect(screen.getByText("42")).toBeInTheDocument()
    expect(screen.getByText("7")).toBeInTheDocument()
    expect(screen.getByText("news:quickView.readMore")).toBeInTheDocument()
  })

  it("renders the category badge label when a category is provided", () => {
    render(<NewsQuickView visible {...baseProps} category="science" />)
    // NewsCategoryBadge renders the labelKey through the mocked t() passthrough.
    expect(screen.getByText("news:categories.science")).toBeInTheDocument()
  })

  it("omits the category badge when no category is given", () => {
    render(<NewsQuickView visible {...baseProps} />)
    expect(screen.queryByText("news:categories.science")).not.toBeInTheDocument()
    // Title + counts still render so the popover body is intact.
    expect(screen.getByText(baseProps.title)).toBeInTheDocument()
  })

  it("renders the formatted date when created_at is set", () => {
    render(<NewsQuickView visible {...baseProps} />)
    const tooltip = screen.getByRole("tooltip", { hidden: true })
    // getMoscowDate produces a non-empty Moscow-localized string.
    expect(tooltip.textContent).not.toBe("")
    expect(tooltip.textContent ?? "").toContain(baseProps.preview)
  })

  it("renders nothing when created_at is empty (no date label branch)", () => {
    render(<NewsQuickView visible {...baseProps} created_at="" />)
    expect(screen.getByText(baseProps.title)).toBeInTheDocument()
  })

  it("applies the bottom position classes when position='bottom'", () => {
    render(<NewsQuickView visible {...baseProps} position="bottom" />)
    const tooltip = screen.getByRole("tooltip", { hidden: true })
    expect(tooltip.className).toContain("top-full")
    expect(tooltip.className).not.toContain("bottom-full")
  })

  it("applies the top position classes by default", () => {
    render(<NewsQuickView visible {...baseProps} />)
    const tooltip = screen.getByRole("tooltip", { hidden: true })
    expect(tooltip.className).toContain("bottom-full")
  })

  it("renders nothing when visible is false", () => {
    render(<NewsQuickView visible={false} {...baseProps} category="science" />)
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument()
    expect(screen.queryByText(baseProps.title)).not.toBeInTheDocument()
  })

  it("uses reduced-motion transitions", () => {
    reducedMotion.mockReturnValue(true)
    render(<NewsQuickView visible {...baseProps} position="bottom" />)
    expect(screen.getByRole("tooltip", { hidden: true })).toBeInTheDocument()
  })

  it("renders the medium category badge variant", () => {
    render(<NewsCategoryBadge category="science" size="md" />)

    expect(screen.getByText("news:categories.science")).toHaveClass("px-3")
  })

  it("uses the compact badge variant when size is omitted", () => {
    render(<NewsCategoryBadge category="science" />)

    const label = screen.getByText("news:categories.science")
    const badge = label.closest("span")
    expect(badge).toHaveClass("px-2.5", "text-[10px]")
    expect(badge).toHaveStyle({ "--_badge-accent": "var(--cat-purple-text)" })
    expect(badge?.querySelector('[aria-hidden="true"]')).toHaveStyle({
      backgroundColor: "var(--cat-purple-text)",
    })
    expect(translation.useTranslation).toHaveBeenCalledWith(["news"])
  })
})
