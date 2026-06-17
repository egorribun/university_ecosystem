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

import { EventDetailNavigation } from "@/components/events/EventDetailNavigation"

const baseProps = {
  prevId: "prev-1",
  nextId: "next-1",
  prevTitle: "Previous Event Title",
  nextTitle: "Next Event Title",
}

describe("EventDetailNavigation", () => {
  it("renders nothing when neither prevId nor nextId is set", () => {
    const { container } = render(
      <EventDetailNavigation prevId={null} nextId={null} prevTitle={null} nextTitle={null} />
    )
    expect(container).toBeEmptyDOMElement()
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument()
  })

  it("renders both prev and next links when both ids are set", () => {
    render(<EventDetailNavigation {...baseProps} />)
    expect(screen.getByRole("navigation", { name: "events:detail.nav.label" })).toBeInTheDocument()
    expect(screen.getByText("events:detail.nav.prev")).toBeInTheDocument()
    expect(screen.getByText("events:detail.nav.next")).toBeInTheDocument()
    expect(screen.getByText("Previous Event Title")).toBeInTheDocument()
    expect(screen.getByText("Next Event Title")).toBeInTheDocument()
    const links = screen.getAllByRole("link")
    expect(links).toHaveLength(2)
    expect(links[0]!).toHaveAttribute("href", "/events/$id/prev-1")
    expect(links[1]!).toHaveAttribute("href", "/events/$id/next-1")
  })

  it("renders only the prev link when nextId is null", () => {
    render(
      <EventDetailNavigation
        prevId="prev-1"
        nextId={null}
        prevTitle="Previous Event Title"
        nextTitle={null}
      />
    )
    expect(screen.getByText("events:detail.nav.prev")).toBeInTheDocument()
    expect(screen.queryByText("events:detail.nav.next")).not.toBeInTheDocument()
    const links = screen.getAllByRole("link")
    expect(links).toHaveLength(1)
    expect(links[0]!).toHaveAttribute("href", "/events/$id/prev-1")
  })

  it("renders only the next link when prevId is null", () => {
    render(
      <EventDetailNavigation
        prevId={null}
        nextId="next-1"
        prevTitle={null}
        nextTitle="Next Event Title"
      />
    )
    expect(screen.getByText("events:detail.nav.next")).toBeInTheDocument()
    expect(screen.queryByText("events:detail.nav.prev")).not.toBeInTheDocument()
    const links = screen.getAllByRole("link")
    expect(links).toHaveLength(1)
    expect(links[0]!).toHaveAttribute("href", "/events/$id/next-1")
  })

  it("renders the nav with a placeholder spacer when only one link is present", () => {
    render(
      <EventDetailNavigation
        prevId="prev-1"
        nextId={null}
        prevTitle="Previous Event Title"
        nextTitle={null}
      />
    )
    const nav = screen.getByRole("navigation", { name: "events:detail.nav.label" })
    expect(nav).toBeInTheDocument()
    // the empty next slot is a flex-1 spacer div, not a link
    expect(nav.querySelectorAll("div.flex-1")).toHaveLength(1)
  })
})
