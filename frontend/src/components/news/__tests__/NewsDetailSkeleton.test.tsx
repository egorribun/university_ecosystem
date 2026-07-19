import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import { NewsDetailSkeleton } from "../NewsDetailSkeleton"

const backdrop = vi.hoisted(() => vi.fn())

vi.mock("@/components/ui", () => ({
  Skeleton: () => <div data-testid="skeleton" />,
}))

vi.mock("../NewsBackdrop", () => ({
  NewsBackdrop: (props: unknown) => {
    backdrop(props)
    return <div data-testid="news-backdrop" />
  },
}))

describe("NewsDetailSkeleton", () => {
  it("passes responsive motion settings to the backdrop and renders every loading region", () => {
    render(<NewsDetailSkeleton isNarrow={true} prefersReducedMotion={true} />)

    expect(screen.getByTestId("news-backdrop")).toBeInTheDocument()
    expect(backdrop).toHaveBeenCalledWith({ isNarrow: true, prefersReducedMotion: true })
    expect(screen.getAllByTestId("skeleton")).toHaveLength(9)
  })
})
