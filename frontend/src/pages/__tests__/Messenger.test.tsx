import type { ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import Messenger from "../Messenger"

vi.mock("@/components/error/FeatureErrorBoundary", () => ({
  FeatureErrorBoundary: ({
    children,
    featureName,
  }: {
    children: ReactNode
    featureName: string
  }) => <div data-feature={featureName}>{children}</div>,
}))
vi.mock("@/features/messenger", () => ({
  MessengerFeature: () => <div data-testid="messenger-feature">messenger content</div>,
}))

describe("Messenger", () => {
  it("keeps the full-screen messenger feature inside its dedicated error boundary", () => {
    render(<Messenger />)

    expect(screen.getByTestId("messenger-feature")).toHaveTextContent("messenger content")
    expect(screen.getByTestId("messenger-feature").parentElement).toHaveAttribute(
      "data-feature",
      "messenger"
    )
  })
})
