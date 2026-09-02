import { useState } from "react"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi } from "vitest"

const { useTranslationMock, translationMock } = vi.hoisted(() => {
  const translationMock = vi.fn((key: string) => key)
  return {
    useTranslationMock: vi.fn(() => ({
      t: translationMock,
      i18n: { language: "en", changeLanguage: () => Promise.resolve() },
    })),
    translationMock,
  }
})

vi.mock("react-i18next", () => ({
  useTranslation: useTranslationMock,
}))

import {
  DEFAULT_EVENT_FILTER_PLACEMENT,
  useEventFilterPopover,
} from "@/components/events/EventFilterPopover"
import type { EventDateRange } from "@/features/events/types"

/**
 * `useEventFilterPopover` is a HEADLESS hook (not a component). Mount it inside
 * a tiny harness that wires a trigger button to `referenceProps` and renders
 * `popoverNode` so we can exercise the real popover render path + callbacks.
 */
function Harness({
  onDateRangeChange,
  onLocationChange,
  initialDateRange = "" as EventDateRange,
  initialLocation = "",
}: {
  onDateRangeChange: (v: EventDateRange) => void
  onLocationChange: (v: string) => void
  initialDateRange?: EventDateRange
  initialLocation?: string
}) {
  const [dateRange, setDateRange] = useState<EventDateRange>(initialDateRange)
  const [location, setLocation] = useState(initialLocation)

  const { referenceProps, filtersActive, popoverNode } = useEventFilterPopover({
    dateRange,
    onDateRangeChange: (v) => {
      setDateRange(v)
      onDateRangeChange(v)
    },
    location,
    onLocationChange: (v) => {
      setLocation(v)
      onLocationChange(v)
    },
  })

  return (
    <div>
      <button {...referenceProps}>open filters</button>
      <span data-testid="active">{String(filtersActive)}</span>
      {popoverNode}
    </div>
  )
}

describe("useEventFilterPopover", () => {
  it("keeps the documented default placement stable", () => {
    expect(DEFAULT_EVENT_FILTER_PLACEMENT).toBe("bottom-end")
  })

  it("opens the popover on trigger click and renders the date quick-buttons", async () => {
    const user = userEvent.setup()
    render(<Harness onDateRangeChange={vi.fn()} onLocationChange={vi.fn()} />)

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    await user.click(screen.getByText("open filters"))

    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(screen.getByText("events:filters.dateRange")).toBeInTheDocument()
    expect(screen.getByText("events:filters.allDates")).toBeInTheDocument()
    expect(screen.getByText("events:filters.today")).toBeInTheDocument()
    expect(screen.getByText("events:filters.thisWeek")).toBeInTheDocument()
    expect(screen.getByText("events:filters.thisMonth")).toBeInTheDocument()
    expect(screen.getByText("events:filters.allDates")).toHaveClass("bg-brand")
    const dialog = screen.getByRole("dialog")
    expect(dialog).toHaveClass(
      "z-modal",
      "min-w-64",
      "rounded-xl",
      "border",
      "border-glass-border",
      "bg-(--bg-surface)/(--opacity-heavy)",
      "p-4",
      "shadow-glass",
      "backdrop-blur-xl"
    )
    expect(screen.getByText("events:filters.allDates")).toHaveClass(
      "rounded-full",
      "px-3",
      "py-1.5",
      "text-xs",
      "font-semibold",
      "transition-colors",
      "duration-fast",
      "focus-visible:ring-2",
      "focus-visible:ring-brand",
      "bg-brand",
      "text-[var(--text-inverse)]",
      "shadow-sm"
    )
    expect(useTranslationMock).toHaveBeenCalledWith(["events", "common"])
    expect(translationMock).toHaveBeenCalledWith("events:filters.dateRange")
  })

  it("fires onDateRangeChange with the right range for each quick-button", async () => {
    const user = userEvent.setup()
    const onDateRangeChange = vi.fn<(v: EventDateRange) => void>()
    render(<Harness onDateRangeChange={onDateRangeChange} onLocationChange={vi.fn()} />)

    await user.click(screen.getByText("open filters"))

    await user.click(screen.getByText("events:filters.today"))
    expect(onDateRangeChange).toHaveBeenLastCalledWith("today")
    expect(screen.getByText("events:filters.today")).toHaveClass("bg-brand")
    expect(screen.getByText("events:filters.allDates")).toHaveClass("matte-chip")

    await user.click(screen.getByText("events:filters.thisWeek"))
    expect(onDateRangeChange).toHaveBeenLastCalledWith("week")

    await user.click(screen.getByText("events:filters.thisMonth"))
    expect(onDateRangeChange).toHaveBeenLastCalledWith("month")
  })

  it("forwards typed location and resets both filters via the Reset button", async () => {
    const user = userEvent.setup()
    const onDateRangeChange = vi.fn<(v: EventDateRange) => void>()
    const onLocationChange = vi.fn<(v: string) => void>()
    render(<Harness onDateRangeChange={onDateRangeChange} onLocationChange={onLocationChange} />)

    await user.click(screen.getByText("open filters"))

    const locationInput = screen.getByLabelText("events:filters.location")
    // This unit test verifies the controlled input contract.  Dispatching one
    // change event keeps the assertion deterministic under Stryker's
    // instrumented runner; realistic character-by-character typing remains
    // covered by the browser journeys.
    fireEvent.change(locationInput, { target: { value: "A" } })
    expect(locationInput).toHaveValue("A")
    await waitFor(() => expect(onLocationChange).toHaveBeenCalledWith("A"))

    await user.click(screen.getByText("common:buttons.reset"))
    await waitFor(() => {
      expect(onDateRangeChange).toHaveBeenLastCalledWith("")
      expect(onLocationChange).toHaveBeenLastCalledWith("")
    })
    expect(screen.getByTestId("active")).toHaveTextContent("false")
  })

  it("closes the popover via the Done button", async () => {
    const user = userEvent.setup()
    render(<Harness onDateRangeChange={vi.fn()} onLocationChange={vi.fn()} />)

    await user.click(screen.getByText("open filters"))
    expect(screen.getByRole("dialog")).toBeInTheDocument()

    await user.click(screen.getByText("common:buttons.done"))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("reports filtersActive=true when a date range or location is preset", () => {
    render(
      <Harness
        onDateRangeChange={vi.fn()}
        onLocationChange={vi.fn()}
        initialDateRange={"today" as EventDateRange}
      />
    )
    expect(screen.getByTestId("active")).toHaveTextContent("true")
  })

  it("reports filtersActive=false when nothing is filtered", () => {
    render(<Harness onDateRangeChange={vi.fn()} onLocationChange={vi.fn()} />)
    expect(screen.getByTestId("active")).toHaveTextContent("false")
  })

  it("treats whitespace-only locations as inactive and meaningful locations as active", () => {
    const { unmount } = render(
      <Harness onDateRangeChange={vi.fn()} onLocationChange={vi.fn()} initialLocation="   " />
    )
    expect(screen.getByTestId("active")).toHaveTextContent("false")

    unmount()
    render(
      <Harness
        onDateRangeChange={vi.fn()}
        onLocationChange={vi.fn()}
        initialLocation=" Main hall "
      />
    )
    expect(screen.getByTestId("active")).toHaveTextContent("true")
  })

  it("treats an unavailable location value as inactive without throwing", () => {
    expect(() =>
      render(
        <Harness
          onDateRangeChange={vi.fn()}
          onLocationChange={vi.fn()}
          initialLocation={undefined as unknown as string}
        />
      )
    ).not.toThrow()
    expect(screen.getByTestId("active")).toHaveTextContent("false")
  })

  it("treats a non-string location value as inactive without coercing it", () => {
    expect(() =>
      render(
        <Harness
          onDateRangeChange={vi.fn()}
          onLocationChange={vi.fn()}
          initialLocation={null as unknown as string}
        />
      )
    ).not.toThrow()
    expect(screen.getByTestId("active")).toHaveTextContent("false")
  })

  it("supports keyboard dismissal of the open popover", async () => {
    const user = userEvent.setup()
    render(<Harness onDateRangeChange={vi.fn()} onLocationChange={vi.fn()} />)
    await user.click(screen.getByText("open filters"))
    expect(screen.getByRole("dialog")).toBeInTheDocument()

    await user.keyboard("{Escape}")
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
  })

  it("supports outside-press dismissal while keeping the trigger contract", async () => {
    const user = userEvent.setup()
    render(<Harness onDateRangeChange={vi.fn()} onLocationChange={vi.fn()} />)
    await user.click(screen.getByText("open filters"))
    expect(screen.getByRole("dialog")).toBeInTheDocument()

    fireEvent.mouseDown(document.body)
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
  })
})
