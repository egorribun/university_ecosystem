import { act, fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi, beforeEach } from "vitest"
import { EventsHeader } from "../EventsHeader"
import useMediaQuery from "@/hooks/useMediaQuery"
import { useSlidingIndicator } from "@/hooks/ui/useSlidingIndicator"

vi.mock("@/hooks/useMediaQuery", () => ({ default: vi.fn(() => false) }))
vi.mock("@/hooks/ui/useSlidingIndicator", () => ({
  useSlidingIndicator: vi.fn(() => null),
}))

// Mock Framer Motion to avoid animation issues in jsdom
vi.mock("framer-motion", async () => {
  const actual = await vi.importActual("framer-motion")
  return {
    ...actual,
    useReducedMotion: () => true,
  }
})

describe("EventsHeader", () => {
  let intersectionCallback: IntersectionObserverCallback | undefined

  const defaultProps = {
    onAddClick: vi.fn(),
    isAdmin: false,
    eventsCount: 42,
    searchQuery: "",
    onSearchChange: vi.fn(),
    activeCategory: "all" as const,
    onCategoryChange: vi.fn(),
    sortMode: "newest" as const,
    onSortChange: vi.fn(),
    tab: "active" as const,
    onTabChange: vi.fn(),
    dateRange: "" as any,
    onDateRangeChange: vi.fn(),
    locationFilter: "",
    onLocationChange: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useMediaQuery).mockReturnValue(false)
    vi.mocked(useSlidingIndicator).mockReturnValue(null)

    // Mock IntersectionObserver
    class MockIntersectionObserver {
      readonly root = null
      readonly rootMargin = "0px"
      readonly scrollMargin = "0px"
      readonly thresholds: readonly number[] = []

      constructor(callback: IntersectionObserverCallback) {
        intersectionCallback = callback
      }

      observe() {}
      unobserve() {}
      disconnect() {}
      takeRecords(): IntersectionObserverEntry[] {
        return []
      }
    }
    window.IntersectionObserver = MockIntersectionObserver
  })

  it("renders correctly", () => {
    render(<EventsHeader {...defaultProps} />)
    expect(screen.getByRole("heading", { name: /Events/i })).toBeInTheDocument()
    expect(screen.getByText("42")).toBeInTheDocument()
  })

  it("shows Add button only for admins", () => {
    const { rerender } = render(<EventsHeader {...defaultProps} isAdmin={false} />)
    expect(screen.queryByText(/\+ Add event/i)).not.toBeInTheDocument()

    rerender(<EventsHeader {...defaultProps} isAdmin={true} />)
    expect(screen.getByText(/\+ Add event/i)).toBeInTheDocument()
  })

  it("calls onAddClick when Add button is clicked", () => {
    render(<EventsHeader {...defaultProps} isAdmin={true} />)
    fireEvent.click(screen.getByText(/\+ Add event/i))
    expect(defaultProps.onAddClick).toHaveBeenCalledTimes(1)
  })

  it("calls onSearchChange when typing in search input", () => {
    render(<EventsHeader {...defaultProps} />)
    const input = screen.getByPlaceholderText(/Search events/i)
    fireEvent.change(input, { target: { value: "hackathon" } })
    expect(defaultProps.onSearchChange).toHaveBeenCalledWith("hackathon")
  })

  it("renders clear button when search is not empty and clears search", () => {
    const { rerender } = render(<EventsHeader {...defaultProps} />)
    expect(screen.queryByLabelText(/Clear search/i)).not.toBeInTheDocument()

    rerender(<EventsHeader {...defaultProps} searchQuery="test" />)
    const clearBtn = screen.getByLabelText(/Clear search/i)
    expect(clearBtn).toBeInTheDocument()

    fireEvent.click(clearBtn)
    expect(defaultProps.onSearchChange).toHaveBeenCalledWith("")
  })

  it("calls onTabChange when a tab is clicked", () => {
    render(<EventsHeader {...defaultProps} />)
    fireEvent.click(screen.getByText(/Past events/i))
    expect(defaultProps.onTabChange).toHaveBeenCalledWith("archive")
  })

  it("calls onCategoryChange when a category is clicked", () => {
    render(<EventsHeader {...defaultProps} />)
    // There should be a generic "all" category first
    fireEvent.click(screen.getByRole("button", { name: /^All$/i }))
    expect(defaultProps.onCategoryChange).toHaveBeenCalledWith("all")
  })

  it("cycles sort mode on click", () => {
    render(<EventsHeader {...defaultProps} sortMode="newest" />)
    // SORT_CYCLE: ["newest", "popular", "upcoming"]
    const sortBtn = screen.getByRole("button", { name: /Sort: Newest/i })
    fireEvent.click(sortBtn)
    expect(defaultProps.onSortChange).toHaveBeenCalledWith("popular")
  })

  it("covers the remaining sort cycle states", () => {
    const { rerender } = render(<EventsHeader {...defaultProps} sortMode="popular" />)
    const sortBtn = screen.getByRole("button", { name: /Sort: Popular/i })
    fireEvent.click(sortBtn)
    expect(defaultProps.onSortChange).toHaveBeenCalledWith("upcoming")

    rerender(<EventsHeader {...defaultProps} sortMode="upcoming" />)
    fireEvent.click(screen.getByRole("button", { name: /Sort: Upcoming/i }))
    expect(defaultProps.onSortChange).toHaveBeenCalledWith("newest")
  })

  it("opens the filter popover, updates values, and resets them", () => {
    render(<EventsHeader {...defaultProps} />)
    fireEvent.click(screen.getByRole("button", { name: /Open filters/i }))

    expect(screen.getByRole("dialog")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: /This week/i }))
    fireEvent.change(screen.getByLabelText(/Location/i), { target: { value: "Main hall" } })
    expect(defaultProps.onDateRangeChange).toHaveBeenCalledWith("week")
    expect(defaultProps.onLocationChange).toHaveBeenCalledWith("Main hall")

    fireEvent.click(screen.getByRole("button", { name: /Reset/i }))
    expect(defaultProps.onDateRangeChange).toHaveBeenCalledWith("")
    expect(defaultProps.onLocationChange).toHaveBeenCalledWith("")
  })

  it("shows active filter state and closes the popover with Done", () => {
    render(<EventsHeader {...defaultProps} dateRange="today" locationFilter="Library" />)
    const filterButton = screen.getByRole("button", { name: /Open filters/i })
    expect(filterButton.className).toContain("text-brand")
    expect(filterButton.querySelector('[aria-hidden="true"]')).toBeInTheDocument()

    fireEvent.click(filterButton)
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: /Done/i }))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("updates sticky state from IntersectionObserver and disconnects on unmount", () => {
    const { container, unmount } = render(<EventsHeader {...defaultProps} />)
    expect(container.querySelector(".events-sticky-categories")).toHaveAttribute(
      "data-stuck",
      "false"
    )

    act(() => {
      intersectionCallback?.([], {} as IntersectionObserver)
    })
    expect(container.querySelector(".events-sticky-categories")).toHaveAttribute(
      "data-stuck",
      "false"
    )

    act(() => {
      intersectionCallback?.(
        [{ isIntersecting: false } as IntersectionObserverEntry],
        {} as IntersectionObserver
      )
    })
    expect(container.querySelector(".events-sticky-categories")).toHaveAttribute(
      "data-stuck",
      "true"
    )

    act(() => {
      intersectionCallback?.(
        [{ isIntersecting: true } as IntersectionObserverEntry],
        {} as IntersectionObserver
      )
    })
    expect(container.querySelector(".events-sticky-categories")).toHaveAttribute(
      "data-stuck",
      "false"
    )
    unmount()
  })

  it("renders the sliding tab indicator with and without reduced motion", () => {
    vi.mocked(useSlidingIndicator).mockReturnValue({ left: 4, top: 2, width: 80, height: 32 })
    const { container, rerender } = render(<EventsHeader {...defaultProps} />)
    const indicator = container.querySelector('[aria-hidden="true"].z-negative')
    expect(indicator).toHaveStyle({
      transform: "translate3d(4px, 2px, 0)",
      width: "80px",
      height: "32px",
    })
    expect(indicator?.getAttribute("style")).toContain("250ms")

    vi.mocked(useMediaQuery).mockReturnValue(true)
    rerender(<EventsHeader {...defaultProps} tab="archive" />)
    expect(container.querySelector('[aria-hidden="true"].z-negative')).toHaveStyle({
      transition: "none",
    })
  })

  it("supports category selection and arrow-key wrapping", () => {
    const onCategoryChange = vi.fn()
    render(
      <EventsHeader
        {...defaultProps}
        activeCategory="lecture"
        onCategoryChange={onCategoryChange}
      />
    )
    const toolbar = screen.getByRole("toolbar")
    const buttons = toolbar.querySelectorAll("button")
    const allButton = buttons[0]!
    const lectureButton = buttons[1]!
    const sortButton = buttons[buttons.length - 1]!

    expect(lectureButton).toHaveAttribute("aria-current", "page")
    fireEvent.click(lectureButton)
    expect(onCategoryChange).toHaveBeenCalledWith("lecture")

    allButton.focus()
    fireEvent.keyDown(toolbar, { key: "ArrowLeft" })
    expect(sortButton).toHaveFocus()
    fireEvent.keyDown(toolbar, { key: "ArrowRight" })
    expect(allButton).toHaveFocus()

    fireEvent.keyDown(toolbar, { key: "Enter" })
    const outsideButton = document.createElement("button")
    document.body.appendChild(outsideButton)
    outsideButton.focus()
    fireEvent.keyDown(toolbar, { key: "ArrowRight" })
    expect(outsideButton).toHaveFocus()
    outsideButton.remove()
  })
})
