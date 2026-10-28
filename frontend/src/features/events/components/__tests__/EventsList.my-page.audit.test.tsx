import { fireEvent, render, screen } from "@testing-library/react"
import type { ButtonHTMLAttributes, ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { Event } from "@/types/Event"
import { EventsList } from "../EventsList"

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }))
vi.mock("@/components/events/EventCard/EventCard", () => ({
  default: ({ id }: { id: string }) => <div>{id}</div>,
}))
vi.mock("@/components/events/EventCard/EventCardSkeleton", () => ({
  EventCardSkeleton: () => <div>loading</div>,
}))
vi.mock("@/components/ui/Button", () => ({
  Button: ({ children, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}))
vi.mock("@/components/ui/EmptyState", () => ({
  EmptyState: ({ title }: { title: ReactNode }) => <div>{title}</div>,
}))
vi.mock("@/components/feedback/OfflineFallback", () => ({ OfflineFallback: () => <div>offline</div> }))
vi.mock("@/components/error", () => ({
  FeatureErrorBoundary: ({ children }: { children: ReactNode }) => <>{children}</>,
}))

const event = { id: "event-1", title: "Event" } as Event
const makeProps = () => ({
  eventsList: [event],
  isInitialLoading: false,
  isFetching: false,
  isFetchingNextPage: false,
  hasNextPage: false,
  fetchNextPage: vi.fn(),
  refreshEvents: vi.fn(),
  onRetry: vi.fn(),
  onAddClick: vi.fn(),
  isAdmin: false,
  isOnline: true,
  tab: "my" as const,
  onTabChange: vi.fn(),
  myPagination: {
    atFirst: false,
    hasPrevious: true,
    hasNext: true,
    onFirst: vi.fn(),
    onPrevious: vi.fn(),
    onNext: vi.fn(),
  },
})

beforeEach(() => {
  vi.stubGlobal("IntersectionObserver", vi.fn())
})

describe("AUD-260 My Events page controls", () => {
  it("uses explicit accessible controls instead of an infinite-scroll observer", () => {
    const props = makeProps()
    render(<EventsList {...props} />)
    const panel = screen.getByRole("tabpanel")
    const first = screen.getByRole("button", { name: "common:pagination.firstPage" })
    const previous = screen.getByRole("button", { name: "common:pagination.prevPage" })
    const next = screen.getByRole("button", { name: "common:pagination.nextPage" })
    expect(first).toHaveClass("min-h-11", "min-w-11")
    expect(previous).toHaveClass("min-h-11", "min-w-11")
    expect(next).toHaveClass("min-h-11", "min-w-11")
    expect(screen.queryByTestId("events-next-page-sentinel")).not.toBeInTheDocument()
    expect(IntersectionObserver).not.toHaveBeenCalled()
    fireEvent.click(next)
    expect(props.myPagination.onNext).toHaveBeenCalledOnce()
    expect(panel).toHaveFocus()
    fireEvent.click(previous)
    expect(props.myPagination.onPrevious).toHaveBeenCalledOnce()
    fireEvent.click(first)
    expect(props.myPagination.onFirst).toHaveBeenCalledOnce()
  })

  it("does not call an empty current page the end while a next page exists", () => {
    render(<EventsList {...makeProps()} eventsList={[]} />)
    expect(screen.queryByText("events:states.empty")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "common:pagination.nextPage" })).toBeEnabled()
  })

  it("keeps navigation available after an error and uses a separate retry callback", () => {
    const props = makeProps()
    render(<EventsList {...props} eventsList={[]} queryError />)
    expect(screen.getByRole("alert")).toHaveTextContent("common:statuses.error")
    expect(screen.getByRole("button", { name: "common:pagination.firstPage" })).toBeEnabled()
    expect(screen.getByRole("button", { name: "common:pagination.prevPage" })).toBeEnabled()
    fireEvent.click(screen.getByRole("button", { name: "common:statuses.tryAgain" }))
    expect(props.onRetry).toHaveBeenCalledOnce()
    expect(props.refreshEvents).not.toHaveBeenCalled()
  })

  it("marks the panel busy and disables page navigation during a request", () => {
    render(<EventsList {...makeProps()} isFetching />)
    expect(screen.getByRole("tabpanel")).toHaveAttribute("aria-busy", "true")
    expect(screen.getByRole("button", { name: "common:pagination.firstPage" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "common:pagination.prevPage" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "common:pagination.nextPage" })).toBeDisabled()
  })
})
