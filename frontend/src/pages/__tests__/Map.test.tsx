import type { ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import MapPage from "../Map"

vi.mock("@/components/Layout", () => ({
  default: ({ children }: { children: ReactNode }) => <div data-testid="layout">{children}</div>,
}))
vi.mock("@/components/motion/PageFadeIn", () => ({
  default: ({ children }: { children: ReactNode }) => <div data-testid="page-fade">{children}</div>,
}))
vi.mock("@/components/error/FeatureErrorBoundary", () => ({
  FeatureErrorBoundary: ({
    children,
    featureName,
  }: {
    children: ReactNode
    featureName: string
  }) => <div data-feature={featureName}>{children}</div>,
}))
vi.mock("@/features/map/MapFeature", () => ({
  MapFeature: () => <div data-testid="map-feature">interactive map</div>,
}))

describe("MapPage", () => {
  it("loads the map feature inside the page layout and its error boundary", async () => {
    render(<MapPage />)

    expect(await screen.findByTestId("map-feature")).toHaveTextContent("interactive map")
    expect(screen.getByTestId("layout")).toBeInTheDocument()
    expect(screen.getByTestId("page-fade")).toBeInTheDocument()
    expect(screen.getByTestId("map-feature").parentElement).toHaveAttribute("data-feature", "map")
  })
})
