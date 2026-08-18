import { cleanup, render, screen } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))
vi.mock("@/components/layout/PageLayout", () => ({
  PageLayout: ({ children }: { children: ReactNode }) => <main>{children}</main>,
}))
vi.mock("@/components/Layout", () => ({
  default: ({ children }: { children: ReactNode }) => <main>{children}</main>,
}))
vi.mock("@/components/ui/SEO", () => ({
  SEO: ({ title }: { title: string }) => <span data-testid="seo">{title}</span>,
}))
vi.mock("@/features/events", () => ({
  EventsFeature: () => <span>events feature</span>,
}))
vi.mock("@/features/news", () => ({
  NewsFeature: () => <span>news feature</span>,
}))

import Events from "@/pages/Events"
import News from "@/pages/News"

afterEach(cleanup)

describe("page entrypoints", () => {
  it("renders the events entrypoint", () => {
    render(<Events />)
    expect(screen.getByText("events feature")).toBeInTheDocument()
  })

  it("renders the news entrypoint and SEO", () => {
    render(<News />)
    expect(screen.getByText("news feature")).toBeInTheDocument()
    expect(screen.getByTestId("seo")).toHaveTextContent("news:pageTitle")
  })
})
