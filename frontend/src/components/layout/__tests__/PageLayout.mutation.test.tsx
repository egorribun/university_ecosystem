import { render, screen } from "@testing-library/react"
import type { ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"

vi.mock("@/components/Layout", () => ({
  default: ({ children }: { children?: ReactNode }) => (
    <div data-testid="page-layout-shell">{children}</div>
  ),
}))

vi.mock("@/components/motion/PageFadeIn", () => ({
  default: ({ children }: { children?: ReactNode }) => (
    <div data-testid="page-layout-fade">{children}</div>
  ),
}))

vi.mock("@/components/ui/SEO", () => ({
  SEO: ({ title, description }: { title?: string; description?: string }) => (
    <div data-testid="page-layout-seo" data-description={description}>
      {title}
    </div>
  ),
}))

import { PageLayout } from "@/components/layout/PageLayout"

describe("PageLayout mutation contracts", () => {
  it.each([
    ["default", "max-w-(--layout-max-page)"],
    ["wide", "max-w-(--layout-max-wide)"],
    ["narrow", "max-w-(--layout-max-content)"],
    ["full", "p-0"],
  ] as const)("preserves the %s content width variant", (variant, expectedVariantClass) => {
    render(
      <PageLayout variant={variant} className="custom-layout">
        page content
      </PageLayout>
    )

    const content = screen.getByText("page content").closest("div.w-full")
    expect(content).toHaveClass("w-full", expectedVariantClass)
    if (variant === "full") {
      expect(content).not.toHaveClass("py-(--fluid-py)")
    } else {
      expect(content).toHaveClass("py-(--fluid-py)")
    }
    expect(content).toHaveClass("custom-layout")
    expect(screen.getByTestId("page-layout-shell")).toBeInTheDocument()
    expect(screen.getByTestId("page-layout-fade")).toBeInTheDocument()
  })

  it("forwards SEO props without adding a title surface when SEO is absent", () => {
    const { rerender } = render(
      <PageLayout seo={{ title: "Profile", description: "Profile overview" }}>profile</PageLayout>
    )

    expect(screen.getByTestId("page-layout-seo")).toHaveTextContent("Profile")
    expect(screen.getByTestId("page-layout-seo")).toHaveAttribute(
      "data-description",
      "Profile overview"
    )

    rerender(<PageLayout>without seo</PageLayout>)
    expect(screen.queryByTestId("page-layout-seo")).not.toBeInTheDocument()
  })
})
