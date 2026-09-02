import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi, beforeEach } from "vitest"

const { filterMock, filterHookMock, useTranslationMock } = vi.hoisted(() => ({
  filterMock: { referenceProps: {}, filtersActive: false, popoverNode: null } as {
    referenceProps: Record<string, unknown>
    filtersActive: boolean
    popoverNode: ReactNode
  },
  filterHookMock: vi.fn(),
  useTranslationMock: vi.fn(() => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  })),
}))

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: useTranslationMock,
}))
vi.mock("@/components/events/EventFilterPopover", () => ({
  useEventFilterPopover: filterHookMock,
}))

import { EventSearchBar } from "@/components/events/EventSearchBar"
import type { EventDateRange } from "@/features/events/types"

const baseProps = {
  search: "",
  onSearchChange: vi.fn(),
  dateRange: "" as EventDateRange,
  onDateRangeChange: vi.fn(),
  location: "",
  onLocationChange: vi.fn(),
}

describe("EventSearchBar", () => {
  beforeEach(() => {
    filterMock.filtersActive = false
    filterMock.popoverNode = null
    filterHookMock.mockReturnValue(filterMock)
  })

  it("renders the search input and filter button", () => {
    render(<EventSearchBar {...baseProps} />)
    const input = screen.getByPlaceholderText("events:filters.search")
    expect(input).toBeInTheDocument()
    expect(input).toHaveClass(
      "w-full",
      "rounded-md",
      "px-4",
      "py-3.5",
      "pl-11",
      "pr-20",
      "text-base",
      "text-text-primary",
      "bg-(--bg-surface)/(--opacity-medium)",
      "border",
      "border-glass-border",
      "shadow-glass",
      "backdrop-blur-md",
      "placeholder:text-(--text-secondary)/(--opacity-medium)",
      "outline-none",
      "transition-all",
      "duration-fast",
      "focus:border-brand/(--opacity-medium)",
      "focus:ring-4",
      "focus:ring-brand/(--opacity-subtle)"
    )
    expect(screen.getByRole("button", { name: "events:aria.openFilters" })).toBeInTheDocument()
    expect(useTranslationMock).toHaveBeenCalledWith(["events"])
    expect(filterHookMock).toHaveBeenCalledWith({
      dateRange: "",
      onDateRangeChange: baseProps.onDateRangeChange,
      location: "",
      onLocationChange: baseProps.onLocationChange,
    })
    expect(screen.queryByLabelText("events:aria.clearSearch")).not.toBeInTheDocument()
  })

  it("shows a clear button only when there is a query and clears it", async () => {
    const user = userEvent.setup()
    const onSearchChange = vi.fn()
    const { rerender } = render(<EventSearchBar {...baseProps} onSearchChange={onSearchChange} />)
    expect(
      screen.queryByRole("button", { name: "events:aria.clearSearch" })
    ).not.toBeInTheDocument()
    rerender(<EventSearchBar {...baseProps} search="react" onSearchChange={onSearchChange} />)
    const clear = screen.getByRole("button", { name: "events:aria.clearSearch" })
    expect(clear).toHaveClass(
      "rounded-full",
      "p-2",
      "text-(--text-secondary)",
      "transition-all",
      "duration-rapid",
      "hover:bg-(--bg-surface)/(--opacity-dim)",
      "active:scale-95"
    )
    await user.click(clear)
    expect(onSearchChange).toHaveBeenCalledWith("")
  })

  it("forwards typed input to onSearchChange", async () => {
    const user = userEvent.setup()
    const onSearchChange = vi.fn()
    render(<EventSearchBar {...baseProps} onSearchChange={onSearchChange} />)
    await user.type(screen.getByPlaceholderText("events:filters.search"), "x")
    expect(onSearchChange).toHaveBeenCalledWith("x")
  })

  it("marks active filters and renders their popover", () => {
    filterMock.filtersActive = true
    filterMock.popoverNode = <div>Filter popover</div>
    render(<EventSearchBar {...baseProps} />)

    expect(screen.getByRole("button", { name: "events:aria.openFilters" })).toHaveClass(
      "text-brand"
    )
    expect(screen.getByText("Filter popover")).toBeInTheDocument()
    expect(document.querySelectorAll('[aria-hidden="true"]')).not.toHaveLength(0)
    expect(document.querySelector("span.bg-brand.shadow-glow-green")).toBeInTheDocument()
    filterMock.popoverNode = null
  })

  it("forwards the headless filter trigger props without replacing them", async () => {
    const user = userEvent.setup()
    const onReferenceClick = vi.fn()
    filterMock.referenceProps = {
      "data-filter-anchor": "events",
      "aria-expanded": true,
      onClick: onReferenceClick,
    }
    render(<EventSearchBar {...baseProps} />)

    const trigger = screen.getByRole("button", { name: "events:aria.openFilters" })
    expect(trigger).toHaveAttribute("data-filter-anchor", "events")
    expect(trigger).toHaveAttribute("aria-expanded", "true")
    await user.click(trigger)
    expect(onReferenceClick).toHaveBeenCalledOnce()
    filterMock.referenceProps = {}
  })

  it("forwards changed filter inputs and keeps the indicator absent when inactive", () => {
    const onDateRangeChange = vi.fn()
    const onLocationChange = vi.fn()
    render(
      <EventSearchBar
        {...baseProps}
        dateRange="week"
        location="Room 3"
        onDateRangeChange={onDateRangeChange}
        onLocationChange={onLocationChange}
      />
    )

    expect(filterHookMock).toHaveBeenCalledWith({
      dateRange: "week",
      onDateRangeChange,
      location: "Room 3",
      onLocationChange,
    })
    expect(screen.getByRole("button", { name: "events:aria.openFilters" })).toHaveClass(
      "text-(--text-secondary)"
    )
    expect(document.querySelector("span.bg-brand.shadow-glow-green")).not.toBeInTheDocument()
  })
})
