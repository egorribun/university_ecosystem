import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock("@/components/ui/SkeletonMorph", () => ({
  SkeletonMorph: ({
    loaded,
    skeleton,
    children,
  }: {
    loaded: boolean
    skeleton: ReactNode
    children: ReactNode
  }) => (loaded ? <>{children}</> : <>{skeleton}</>),
}))

vi.mock("../AnimatedRing", () => ({
  default: ({ value, max }: { value: number; max: number }) => (
    <span data-testid="animated-ring">
      {value}/{max}
    </span>
  ),
  useAnimatedNumber: (value: number) => value,
}))

vi.mock("../CardShell", () => ({
  default: ({ children, ...props }: { children: ReactNode }) => (
    <section {...props}>{children}</section>
  ),
}))

vi.mock("../TrendChip", () => ({
  default: ({ value }: { value?: number }) => <span data-testid="trend">{String(value)}</span>,
}))

import { GradesCard } from "../GradesCard"

describe("GradesCard scale and loading branches", () => {
  it("renders the loading skeleton before the first response", () => {
    render(<GradesCard hasInitiallyLoaded={false} ringSize={64} />)
    expect(screen.queryByTestId("animated-ring")).not.toBeInTheDocument()
    expect(document.querySelector(".animate-pulse")).toBeInTheDocument()
  })

  it("renders GPA formatting and precision", () => {
    render(
      <GradesCard
        hasInitiallyLoaded
        ringSize={64}
        grades={{ average: 3.25, scale: "gpa", trend: 1.2, recent: [] }}
      />
    )
    expect(screen.getByTestId("animated-ring")).toHaveTextContent("3.25/4")
    expect(screen.getByText("GPA 3.25")).toBeInTheDocument()
    expect(screen.getByTestId("trend")).toHaveTextContent("1.2")
  })

  it("renders 100-point formatting and rounds the animated value", () => {
    render(
      <GradesCard
        hasInitiallyLoaded
        ringSize={64}
        grades={{ average: 87.6, scale: "100", trend: -2, recent: [] }}
      />
    )
    expect(screen.getByTestId("animated-ring")).toHaveTextContent("87.6/100")
    expect(screen.getByText("88/100")).toBeInTheDocument()
  })

  it("uses the five-point fallback scale for absent or five-point grades", () => {
    const { rerender } = render(<GradesCard hasInitiallyLoaded ringSize={64} grades={null} />)
    expect(screen.getByTestId("animated-ring")).toHaveTextContent("0/5")

    rerender(
      <GradesCard
        hasInitiallyLoaded
        ringSize={64}
        grades={{ average: 4.5, scale: "5", trend: 0, recent: [] }}
      />
    )
    expect(screen.getByTestId("animated-ring")).toHaveTextContent("4.5/5")
    expect(screen.getByTestId("trend")).toHaveTextContent("0")
  })
})
