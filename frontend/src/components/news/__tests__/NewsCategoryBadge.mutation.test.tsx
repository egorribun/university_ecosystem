import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  getCategoryMeta: vi.fn(() => ({
    labelKey: "news:categories.campus",
    color: "sky",
  })),
  t: vi.fn((key: string, options?: { defaultValue?: string }) => options?.defaultValue ?? key),
  useTranslation: vi.fn(),
}))

vi.mock("@/features/news/categories", () => ({
  getCategoryMeta: mocks.getCategoryMeta,
}))

vi.mock("react-i18next", () => ({
  useTranslation: mocks.useTranslation,
}))

import { NewsCategoryBadge } from "@/components/news/NewsCategoryBadge"

describe("NewsCategoryBadge mutation contracts", () => {
  beforeEach(() => {
    mocks.getCategoryMeta.mockClear()
    mocks.t.mockClear()
    mocks.useTranslation.mockReset().mockReturnValue({ t: mocks.t })
  })

  it("renders the translated small badge and preserves the category accent dot", () => {
    render(<NewsCategoryBadge category="campus" />)

    expect(mocks.useTranslation).toHaveBeenCalledWith(["news"])
    expect(mocks.getCategoryMeta).toHaveBeenCalledWith("campus")
    expect(mocks.t).toHaveBeenCalledWith("news:categories.campus", { defaultValue: "campus" })

    const badge = screen.getByText("campus").closest(".news-badge-matte")
    expect(badge).toHaveClass(
      "news-badge-matte",
      "inline-flex",
      "items-center",
      "rounded-full",
      "px-2.5",
      "py-0.5",
      "text-[10px]",
      "font-bold",
      "uppercase",
      "tracking-wider"
    )
    expect(badge).toHaveStyle("--_badge-accent: var(--cat-sky-text)")

    const dot = badge?.querySelector('span[aria-hidden="true"]')
    expect(dot).toHaveClass("mr-1", "inline-block", "h-1.5", "w-1.5", "rounded-full")
    expect(dot).toHaveAttribute("aria-hidden", "true")
    expect(dot).toHaveStyle("background-color: var(--cat-sky-text)")
  })

  it("supports the larger badge size without changing its localized label", () => {
    render(<NewsCategoryBadge category="campus" size="md" />)

    const badge = screen.getByText("campus").closest(".news-badge-matte")
    expect(badge).toHaveClass(
      "news-badge-matte",
      "inline-flex",
      "items-center",
      "rounded-full",
      "px-3",
      "py-1",
      "text-xs",
      "font-bold",
      "uppercase",
      "tracking-wider"
    )
    expect(screen.getByText("campus")).toBeInTheDocument()
  })
})
