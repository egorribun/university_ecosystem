import { render, screen } from "@testing-library/react"
import type { ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"

vi.mock("@/components/Layout", () => ({
  default: ({ children }: { children?: ReactNode }) => (
    <div data-testid="profile-skeleton-layout">{children}</div>
  ),
}))

vi.mock("@/components/motion/PageFadeIn", () => ({
  default: ({ children }: { children?: ReactNode }) => (
    <div data-testid="profile-skeleton-fade">{children}</div>
  ),
}))

vi.mock("@/components/ui", () => ({
  Card: ({ children, className }: { children?: ReactNode; className?: string }) => (
    <section data-testid="profile-skeleton-card" className={className}>
      {children}
    </section>
  ),
  Skeleton: ({
    width,
    height,
    rounded,
    className,
  }: {
    width?: number | string
    height?: number | string
    rounded?: string
    className?: string
  }) => (
    <div
      data-testid="profile-skeleton-cell"
      data-width={String(width)}
      data-height={String(height)}
      data-rounded={rounded}
      className={className}
    />
  ),
}))

import { ProfileSkeleton } from "@/components/profile/ProfileSkeleton"

describe("ProfileSkeleton mutation contracts", () => {
  it("renders the complete predictable loading geometry", () => {
    render(<ProfileSkeleton />)

    expect(screen.getByTestId("profile-skeleton-layout")).toBeInTheDocument()
    expect(screen.getByTestId("profile-skeleton-fade")).toBeInTheDocument()
    expect(screen.getByTestId("profile-skeleton-card")).toHaveClass("overflow-hidden")

    const cells = screen.getAllByTestId("profile-skeleton-cell")
    expect(cells).toHaveLength(10)

    expect(cells[0]).toHaveAttribute("data-width", "100%")
    expect(cells[0]).toHaveAttribute("data-height", "100%")
    expect(cells[1]).toHaveAttribute("data-width", "160")
    expect(cells[1]).toHaveAttribute("data-height", "160")
    expect(cells[1]).toHaveAttribute("data-rounded", "50%")
    expect(cells[1]).toHaveClass("border-4", "border-(--bg-surface)")
    expect(cells[2]).toHaveAttribute("data-width", "300")
    expect(cells[2]).toHaveAttribute("data-height", "48")
    expect(cells[3]).toHaveAttribute("data-width", "200")
    expect(cells[3]).toHaveAttribute("data-height", "24")

    expect(cells.slice(4, 8)).toHaveLength(4)
    for (const cell of cells.slice(4, 8)) {
      expect(cell).toHaveAttribute("data-width", "100%")
      expect(cell).toHaveAttribute("data-height", "3rem")
      expect(cell).toHaveAttribute("data-rounded", "md")
    }

    expect(cells[8]).toHaveAttribute("data-height", "7.5rem")
    expect(cells[8]).toHaveAttribute("data-rounded", "lg")
    expect(cells[9]).toHaveAttribute("data-height", "12.5rem")
    expect(cells[9]).toHaveAttribute("data-rounded", "lg")
  })
})
