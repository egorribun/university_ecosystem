import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))
vi.mock("@tanstack/react-router", () => ({
  Link: ({
    children,
    to,
    params,
    ...rest
  }: { children?: ReactNode; to?: string; params?: { id?: string } } & Record<string, unknown>) => (
    <a href={`${to}/${params?.id ?? ""}`} {...rest}>
      {children}
    </a>
  ),
}))

import { NewsDetailNavigation } from "@/components/news/NewsDetailNavigation"

const baseProps = {
  prevId: "prev-1",
  nextId: "next-1",
  prevTitle: "Previous Article Title",
  nextTitle: "Next Article Title",
}

describe("NewsDetailNavigation", () => {
  it("renders nothing when neither prevId nor nextId is set", () => {
    const { container } = render(
      <NewsDetailNavigation prevId={null} nextId={null} prevTitle={null} nextTitle={null} />
    )
    expect(container).toBeEmptyDOMElement()
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument()
  })

  it("renders both prev and next links when both ids are set", () => {
    render(<NewsDetailNavigation {...baseProps} />)
    expect(screen.getByRole("navigation", { name: "news:navigation.label" })).toBeInTheDocument()
    expect(screen.getByText("news:navigation.prev")).toBeInTheDocument()
    expect(screen.getByText("news:navigation.next")).toBeInTheDocument()
    expect(screen.getByText("Previous Article Title")).toBeInTheDocument()
    expect(screen.getByText("Next Article Title")).toBeInTheDocument()
    const links = screen.getAllByRole("link")
    expect(links).toHaveLength(2)
    expect(links[0]!).toHaveAttribute("href", "/news/$id/prev-1")
    expect(links[1]!).toHaveAttribute("href", "/news/$id/next-1")
  })

  it("renders only the prev link with a spacer when nextId is null", () => {
    render(
      <NewsDetailNavigation
        prevId="prev-1"
        nextId={null}
        prevTitle="Previous Article Title"
        nextTitle={null}
      />
    )
    expect(screen.getByText("news:navigation.prev")).toBeInTheDocument()
    expect(screen.queryByText("news:navigation.next")).not.toBeInTheDocument()
    const links = screen.getAllByRole("link")
    expect(links).toHaveLength(1)
    expect(links[0]!).toHaveAttribute("href", "/news/$id/prev-1")
    const nav = screen.getByRole("navigation", { name: "news:navigation.label" })
    // empty next slot is a flex-1 spacer div, not a link.
    expect(nav.querySelectorAll("div.flex-1")).toHaveLength(1)
  })

  it("renders only the next link with a spacer when prevId is null", () => {
    render(
      <NewsDetailNavigation
        prevId={null}
        nextId="next-1"
        prevTitle={null}
        nextTitle="Next Article Title"
      />
    )
    expect(screen.getByText("news:navigation.next")).toBeInTheDocument()
    expect(screen.queryByText("news:navigation.prev")).not.toBeInTheDocument()
    const links = screen.getAllByRole("link")
    expect(links).toHaveLength(1)
    expect(links[0]!).toHaveAttribute("href", "/news/$id/next-1")
    const nav = screen.getByRole("navigation", { name: "news:navigation.label" })
    expect(nav.querySelectorAll("div.flex-1")).toHaveLength(1)
  })
})
