import { render, screen, fireEvent } from "@testing-library/react"
import { describe, expect, it, vi, beforeEach } from "vitest"
import { EventsHeader } from "../EventsHeader"

// Mock Framer Motion to avoid animation issues in jsdom
vi.mock("framer-motion", async () => {
  const actual = await vi.importActual("framer-motion")
  return {
    ...actual,
    useReducedMotion: () => true,
  }
})

describe("EventsHeader", () => {
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

    // Mock IntersectionObserver
    const mockIntersectionObserver = vi.fn()
    mockIntersectionObserver.mockReturnValue({
      observe: () => null,
      unobserve: () => null,
      disconnect: () => null,
    })
    window.IntersectionObserver = mockIntersectionObserver
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
})
