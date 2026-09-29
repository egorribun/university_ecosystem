import { fireEvent, render, screen } from "@testing-library/react"
import type { ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const translation = vi.hoisted(() => ({
  useTranslation: vi.fn((namespaces?: string | string[]) => ({
    t: (key: string) => key,
    namespaces,
  })),
  motion: {
    props: undefined as Record<string, unknown> | undefined,
  },
}))

vi.mock("react-i18next", () => ({
  useTranslation: translation.useTranslation,
}))

vi.mock("framer-motion", () => ({
  AnimatePresence: ({ children }: { children: ReactNode }) => <>{children}</>,
  m: {
    div: (props: Record<string, unknown>) => {
      translation.motion.props = props
      return <div data-testid="expanded-summary-content">{props.children as ReactNode}</div>
    },
  },
}))

import { ContentSummary } from "@/components/ui/ContentSummary"

describe("ContentSummary mutation contracts", () => {
  beforeEach(() => {
    translation.useTranslation.mockClear()
    translation.motion.props = undefined
  })

  it("renders children directly when no summary is available and not loading", () => {
    render(
      <ContentSummary summary={null}>
        <span>full content</span>
      </ContentSummary>
    )

    expect(screen.getByText("full content")).toBeInTheDocument()
    expect(screen.queryByText("common:ai.summaryBadge")).not.toBeInTheDocument()
  })

  it("requests the common namespace and renders the complete collapsed summary", () => {
    render(
      <ContentSummary summary="A concise summary" className="summary-shell">
        <span>full content</span>
      </ContentSummary>
    )

    expect(translation.useTranslation).toHaveBeenCalledWith(["common"])
    const shell = screen.getByText("common:ai.summaryBadge").closest(".summary-shell")
    expect(shell).toHaveClass("space-y-3", "summary-shell")
    expect(screen.getByText("A concise summary")).toHaveClass(
      "text-sm",
      "font-medium",
      "leading-relaxed",
      "text-text-secondary"
    )
    const toggle = screen.getByRole("button", { name: "common:ai.readMore" })
    expect(toggle).toHaveAttribute("aria-expanded", "false")
    expect(toggle.querySelector("svg")).toHaveClass(
      "h-3.5",
      "w-3.5",
      "transition-transform",
      "duration-base"
    )
  })

  it("shows loading skeletons without summary controls while loading", () => {
    const { container } = render(
      <ContentSummary summary={null} loading>
        <span>full content</span>
      </ContentSummary>
    )

    expect(container.querySelectorAll(".animate-pulse")).toHaveLength(2)
    expect(screen.queryByRole("button")).not.toBeInTheDocument()
    expect(screen.queryByText("full content")).not.toBeInTheDocument()
  })

  it("toggles expansion labels, aria state, icon rotation, and motion contract", () => {
    render(
      <ContentSummary summary="A concise summary">
        <span>full content</span>
      </ContentSummary>
    )

    const toggle = screen.getByRole("button", { name: "common:ai.readMore" })
    fireEvent.click(toggle)

    expect(screen.getByRole("button", { name: "common:ai.showLess" })).toHaveAttribute(
      "aria-expanded",
      "true"
    )
    expect(screen.getByTestId("expanded-summary-content")).toContainElement(
      screen.getByText("full content")
    )
    expect(toggle.querySelector("svg")).toHaveClass("rotate-180")
    expect(translation.motion.props).toMatchObject({
      initial: { height: 0, opacity: 0 },
      animate: { height: "auto", opacity: 1 },
      exit: { height: 0, opacity: 0 },
      transition: { duration: 0.3, ease: [0.16, 1, 0.3, 1] },
      className: "overflow-hidden",
    })

    fireEvent.click(screen.getByRole("button", { name: "common:ai.showLess" }))
    expect(screen.getByRole("button", { name: "common:ai.readMore" })).toHaveAttribute(
      "aria-expanded",
      "false"
    )
  })
})
