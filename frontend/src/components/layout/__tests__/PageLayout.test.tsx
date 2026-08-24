import { render, screen } from "@testing-library/react"
import type { ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"

vi.mock("@/components/Layout", () => ({
  default: ({ children }: { children: ReactNode }) => <main>{children}</main>,
}))
vi.mock("@/components/motion/PageFadeIn", () => ({
  default: ({ children }: { children: ReactNode }) => <>{children}</>,
}))
vi.mock("@/components/ui/SEO", () => ({
  SEO: ({ title }: { title?: string }) => <span data-testid="seo">{title}</span>,
}))

import { PageLayout } from "@/components/layout/PageLayout"

describe("PageLayout", () => {
  it("renders its runtime dependencies, SEO, and selected layout variant", () => {
    render(
      <PageLayout variant="narrow" className="custom" seo={{ title: "Profile" }}>
        content
      </PageLayout>
    )

    expect(screen.getByTestId("seo")).toHaveTextContent("Profile")
    expect(screen.getByText("content")).toHaveClass("max-w-(--layout-max-content)", "custom")
  })

  it("uses the default variant without SEO", () => {
    render(<PageLayout>default content</PageLayout>)

    expect(screen.queryByTestId("seo")).not.toBeInTheDocument()
    expect(screen.getByText("default content")).toHaveClass("max-w-(--layout-max-page)")
  })
})
