import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi, beforeEach } from "vitest"

const { filterMock } = vi.hoisted(() => ({
  filterMock: { referenceProps: {}, filtersActive: false, popoverNode: null } as {
    referenceProps: Record<string, unknown>
    filtersActive: boolean
    popoverNode: ReactNode
  },
}))

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))
vi.mock("@/components/events/EventFilterPopover", () => ({
  useEventFilterPopover: () => filterMock,
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
  })

  it("renders the search input and filter button", () => {
    render(<EventSearchBar {...baseProps} />)
    expect(screen.getByPlaceholderText("events:filters.search")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "events:aria.openFilters" })).toBeInTheDocument()
  })

  it("shows a clear button only when there is a query and clears it", async () => {
    const user = userEvent.setup()
    const onSearchChange = vi.fn()
    const { rerender } = render(<EventSearchBar {...baseProps} onSearchChange={onSearchChange} />)
    expect(
      screen.queryByRole("button", { name: "events:aria.clearSearch" })
    ).not.toBeInTheDocument()
    rerender(<EventSearchBar {...baseProps} search="react" onSearchChange={onSearchChange} />)
    await user.click(screen.getByRole("button", { name: "events:aria.clearSearch" }))
    expect(onSearchChange).toHaveBeenCalledWith("")
  })

  it("forwards typed input to onSearchChange", async () => {
    const user = userEvent.setup()
    const onSearchChange = vi.fn()
    render(<EventSearchBar {...baseProps} onSearchChange={onSearchChange} />)
    await user.type(screen.getByPlaceholderText("events:filters.search"), "x")
    expect(onSearchChange).toHaveBeenCalledWith("x")
  })
})
