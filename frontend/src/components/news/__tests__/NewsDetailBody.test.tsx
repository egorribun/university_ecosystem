import { render, screen } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach } from "vitest"

const { mediaMock } = vi.hoisted(() => ({ mediaMock: vi.fn() }))

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))
vi.mock("@/hooks/useMediaQuery", () => ({ default: () => mediaMock() }))

import { NewsDetailBody } from "@/components/news/NewsDetailBody"

const MARKDOWN_WITH_TOC = `## Background

The university opened a new interdisciplinary lab this spring.

## Methodology

We surveyed enrolment data across three faculties.

## Key Findings

Enrolment rose by a double-digit margin year over year.`

const PLAIN_TEXT = `The new facility is the largest investment in a decade.

It will host robotics, AI, and data-science tracks under one roof.`

describe("NewsDetailBody", () => {
  beforeEach(() => {
    mediaMock.mockReset()
    mediaMock.mockReturnValue(true) // desktop
  })

  it("renders markdown headings and the table of contents on desktop", () => {
    render(<NewsDetailBody content={MARKDOWN_WITH_TOC} />)
    expect(screen.getByRole("heading", { name: "Background" })).toBeInTheDocument()
    expect(screen.getByText("news:toc.title")).toBeInTheDocument()
  })

  it("renders plain-text content as paragraphs", () => {
    render(<NewsDetailBody content={PLAIN_TEXT} />)
    expect(
      screen.getByText("The new facility is the largest investment in a decade.")
    ).toBeInTheDocument()
    expect(screen.queryByText("news:toc.title")).not.toBeInTheDocument()
  })

  it("renders nothing in the body for empty content without throwing", () => {
    expect(() => render(<NewsDetailBody content="" />)).not.toThrow()
    expect(screen.queryByText("news:toc.title")).not.toBeInTheDocument()
  })
})
