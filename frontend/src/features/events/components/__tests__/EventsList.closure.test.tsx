import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { ButtonHTMLAttributes, ReactNode } from "react"

import type { Event } from "@/types/Event"
import { EventsList } from "../EventsList"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

vi.mock("@/components/events/EventCard/EventCard", () => ({
  default: ({ id, onChange }: { id: string; onChange: () => void }) => (
    <button type="button" data-testid={`event-${id}`} onClick={onChange}>
      {id}
    </button>
  ),
}))

vi.mock("@/components/events/EventCard/EventCardSkeleton", () => ({
  EventCardSkeleton: () => <div data-testid="event-skeleton" />,
}))

vi.mock("@/components/feedback/OfflineFallback", () => ({
  default: ({ onRetry }: { onRetry: () => void }) => (
    <button type="button" onClick={onRetry}>
      offline-retry
    </button>
  ),
}))

vi.mock("@/components/ui", () => ({
  Button: ({ children, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button type="button" {...props}>
      {children}
    </button>
  ),
}))

vi.mock("@/components/ui/EmptyState", () => ({
  EmptyState: ({
    title,
    description,
    action,
  }: {
    title: ReactNode
    description: ReactNode
    action?: ReactNode
  }) => (
    <div>
      <h2>{title}</h2>
      <p>{description}</p>
      {action}
    </div>
  ),
}))

vi.mock("@/components/error", () => ({
  FeatureErrorBoundary: ({ children }: { children: ReactNode }) => <>{children}</>,
}))

const event = (id: string) => ({ id, title: `Event ${id}` }) as unknown as Event

const baseProps = {
  eventsList: [],
  isInitialLoading: false,
  isFetching: false,
  isFetchingNextPage: false,
  hasNextPage: false,
  fetchNextPage: vi.fn(),
  refreshEvents: vi.fn(),
  onAddClick: vi.fn(),
  isAdmin: false,
  isOnline: true,
  tab: "active" as const,
  onTabChange: vi.fn(),
}

let intersectionCallback: IntersectionObserverCallback | undefined
const observe = vi.fn()
const disconnect = vi.fn()

beforeEach(() => {
  vi.clearAllMocks()
  intersectionCallback = undefined
  class TestIntersectionObserver {
    constructor(callback: IntersectionObserverCallback) {
      intersectionCallback = callback
    }

    observe(target: Element) {
      observe(target)
    }

    disconnect() {
      disconnect()
    }
  }
  Object.defineProperty(globalThis, "IntersectionObserver", {
    configurable: true,
    writable: true,
    value: TestIntersectionObserver,
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("EventsList closure", () => {
  it("renders the full initial loading skeleton set inside the tabpanel", () => {
    render(<EventsList {...baseProps} isInitialLoading />)

    expect(screen.getByRole("tabpanel")).toHaveAttribute("aria-busy", "true")
    expect(screen.getAllByTestId("event-skeleton")).toHaveLength(6)
    expect(screen.queryByText("events:states.empty")).not.toBeInTheDocument()
  })

  it("renders the offline empty state and retries through the stable callback", () => {
    const refreshEvents = vi.fn()
    render(<EventsList {...baseProps} isOnline={false} refreshEvents={refreshEvents} />)

    fireEvent.click(screen.getByRole("button", { name: "offline-retry" }))

    expect(refreshEvents).toHaveBeenCalledOnce()
  })

  it("renders online empty-state actions for active, archive, and admin tabs", () => {
    const onTabChange = vi.fn()
    const view = render(
      <EventsList {...baseProps} tab="active" onTabChange={onTabChange} eventsList={[]} />
    )
    fireEvent.click(screen.getByRole("button", { name: "events:tabs.archive" }))
    expect(onTabChange).toHaveBeenCalledWith("archive")

    view.rerender(
      <EventsList {...baseProps} tab="archive" onTabChange={onTabChange} eventsList={[]} />
    )
    fireEvent.click(screen.getByRole("button", { name: "events:tabs.active" }))
    expect(onTabChange).toHaveBeenCalledWith("active")

    view.rerender(<EventsList {...baseProps} tab="my" eventsList={[]} />)
    expect(
      screen.queryByRole("button", { name: "events:actions.openCreate" })
    ).not.toBeInTheDocument()

    const onAddClick = vi.fn()
    view.rerender(
      <EventsList
        {...baseProps}
        tab="my"
        isAdmin
        onAddClick={onAddClick}
        onTabChange={onTabChange}
        eventsList={[]}
      />
    )
    fireEvent.click(screen.getByRole("button", { name: "events:actions.openCreate" }))
    expect(onAddClick).toHaveBeenCalledOnce()
  })

  it("renders cards, refetch indicator, next-page skeletons, refs, and sentinel", () => {
    const refreshEvents = vi.fn()
    const fetchNextPage = vi.fn()
    const registerCardRef = vi.fn()
    const view = render(
      <EventsList
        {...baseProps}
        eventsList={[event("one"), event("two")]}
        isFetching
        hasNextPage
        fetchNextPage={fetchNextPage}
        refreshEvents={refreshEvents}
        activeKeyboardIndex={1}
        registerCardRef={registerCardRef}
      />
    )

    expect(screen.getByText("one")).toBeInTheDocument()
    expect(screen.getByText("two").parentElement).toHaveClass("ring-2")
    expect(screen.getByRole("tabpanel")).toContainHTML("animate-pulse")
    expect(registerCardRef).toHaveBeenCalledWith(0, expect.anything())
    expect(registerCardRef).toHaveBeenCalledWith(1, expect.anything())
    fireEvent.click(screen.getByTestId("event-one"))
    expect(refreshEvents).toHaveBeenCalledOnce()

    expect(intersectionCallback).toBeDefined()
    intersectionCallback?.(
      [{ isIntersecting: false } as IntersectionObserverEntry],
      {} as IntersectionObserver
    )
    expect(fetchNextPage).not.toHaveBeenCalled()
    intersectionCallback?.(
      [{ isIntersecting: true } as IntersectionObserverEntry],
      {} as IntersectionObserver
    )
    expect(fetchNextPage).toHaveBeenCalledOnce()

    view.rerender(
      <EventsList {...baseProps} eventsList={[event("one")]} isFetchingNextPage hasNextPage />
    )
    expect(screen.getAllByTestId("event-skeleton")).toHaveLength(3)
    expect(disconnect).toHaveBeenCalled()
  })

  it("does not create an observer while the next page is already fetching", () => {
    render(<EventsList {...baseProps} eventsList={[event("one")]} hasNextPage isFetchingNextPage />)

    expect(observe).not.toHaveBeenCalled()
  })
})
