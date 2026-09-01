import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

const backdrop = vi.hoisted(() => vi.fn())

vi.mock("@/components/ui", () => ({
  Skeleton: ({
    width,
    height,
    rounded,
    className,
  }: {
    width?: number | string
    height?: number | string
    rounded?: boolean | string
    className?: string
  }) => (
    <div
      data-testid="news-detail-skeleton-cell"
      data-width={String(width)}
      data-height={String(height)}
      data-rounded={String(rounded)}
      className={className}
    />
  ),
}))

vi.mock("../NewsBackdrop", () => ({
  NewsBackdrop: (props: { isNarrow: boolean; prefersReducedMotion: boolean }) => {
    backdrop(props)
    return <div data-testid="news-detail-backdrop" />
  },
}))

import { NewsDetailSkeleton } from "@/components/news/NewsDetailSkeleton"

describe("NewsDetailSkeleton mutation contracts", () => {
  it("preserves responsive backdrop props and the non-rounded hero media placeholder", () => {
    render(<NewsDetailSkeleton isNarrow={true} prefersReducedMotion={true} />)

    expect(backdrop).toHaveBeenCalledWith({ isNarrow: true, prefersReducedMotion: true })
    const cells = screen.getAllByTestId("news-detail-skeleton-cell")
    expect(cells).toHaveLength(9)

    const heroMedia = cells.find((cell) => cell.getAttribute("data-height") === "22rem")
    expect(heroMedia).toBeDefined()
    expect(heroMedia).toHaveAttribute("data-rounded", "false")
    expect(heroMedia).toHaveClass("w-full")
  })
})
