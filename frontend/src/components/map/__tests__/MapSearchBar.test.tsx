import { act, fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, it, expect, vi } from "vitest"

const translation = vi.hoisted(() => {
  const translate = (key: string, options?: Record<string, unknown>) =>
    options && Object.keys(options).length > 0 ? `${key}|${JSON.stringify(options)}` : key
  const t = vi.fn(translate)
  const useTranslation = vi.fn(() => ({
    t,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }))
  return { t, translate, useTranslation }
})

vi.mock("react-i18next", () => ({ useTranslation: translation.useTranslation }))

import {
  applySearchSelection,
  blurSearchInput,
  focusSearchInput,
  MapSearchBar,
} from "@/components/map/MapSearchBar"
import type { CampusBuilding } from "@/data/campusBuildings"

const BUILDING: CampusBuilding = {
  letter: "ГУК",
  structureId: "стр. 8",
  name: "Главный учебный корпус",
  description: "Главное здание университета.",
  address: "Рязанский проспект, 99",
  hours: { weekday: "08:00–22:00", saturday: "09:00–20:00", sunday: "Закрыто" },
  amenities: ["Wi-Fi"],
  tags: ["study"],
  colorVar: "var(--color-blue-500)",
  colorHex: "#3b82f6",
  floorCount: 1,
  floors: [
    {
      floor: 1,
      rooms: [
        { id: "ГУК-101", number: "101", name: "Большая аудитория", type: "lecture" },
        { id: "ГУК-102", number: "102", type: "seminar" },
      ],
    },
  ],
  geoCoords: [55.71, 37.81],
}

const baseProps = {
  buildings: [BUILDING],
  onSelectBuilding: vi.fn(),
  onSelectRoom: vi.fn(),
}

const CAMPUS_BUILDINGS: CampusBuilding[] = [
  { ...BUILDING, name: "Campus Main" },
  {
    ...BUILDING,
    letter: "ЛК",
    name: "Campus Annex",
    floorCount: 2,
    floors: [
      {
        floor: 2,
        rooms: [{ id: "ЛК-201", number: "201", name: "Seminar Room", type: "seminar" }],
      },
    ],
  },
]

const MANY_ROOM_BUILDING: CampusBuilding = {
  ...BUILDING,
  name: "Rooms Building",
  floors: [
    {
      floor: 1,
      rooms: Array.from({ length: 13 }, (_, index) => ({
        id: `ROOM-${index + 1}`,
        number: String(index + 1),
        name: `Room ${index + 1}`,
        type: "seminar" as const,
      })),
    },
  ],
}

afterEach(() => {
  translation.t.mockImplementation(translation.translate)
})

describe("MapSearchBar", () => {
  it("ignores a missing selection without invoking either callback", () => {
    const onSelectBuilding = vi.fn()
    const onSelectRoom = vi.fn()
    const onSelectionApplied = vi.fn()

    expect(
      applySearchSelection(undefined, onSelectBuilding, onSelectRoom, onSelectionApplied)
    ).toBe(false)
    expect(onSelectBuilding).not.toHaveBeenCalled()
    expect(onSelectRoom).not.toHaveBeenCalled()
    expect(onSelectionApplied).not.toHaveBeenCalled()
  })

  it("keeps nullable focus helpers total while exercising the applied callback", () => {
    const input = document.createElement("input")
    const blur = vi.spyOn(input, "blur")
    const focus = vi.spyOn(input, "focus")
    const onSelectionApplied = vi.fn()

    blurSearchInput(null)
    focusSearchInput(null)
    blurSearchInput(input)
    focusSearchInput(input)
    applySearchSelection(
      { type: "building", buildingLetter: "ГУК", label: "Main" },
      vi.fn(),
      vi.fn(),
      onSelectionApplied
    )

    expect(blur).toHaveBeenCalledOnce()
    expect(focus).toHaveBeenCalledOnce()
    expect(onSelectionApplied).toHaveBeenCalledOnce()
  })

  it("applies a valid selection when the completion callback is omitted", () => {
    const onSelectBuilding = vi.fn()
    const onSelectRoom = vi.fn()

    expect(
      applySearchSelection(
        { type: "building", buildingLetter: "ГУК", label: "Main" },
        onSelectBuilding,
        onSelectRoom
      )
    ).toBe(true)
    expect(onSelectBuilding).toHaveBeenCalledWith("ГУК")
    expect(onSelectRoom).not.toHaveBeenCalled()
  })

  it("rejects stale result variants without invoking selection callbacks", () => {
    const onSelectBuilding = vi.fn()
    const onSelectRoom = vi.fn()
    const staleResult = { type: "stale" } as unknown as Parameters<typeof applySearchSelection>[0]

    expect(applySearchSelection(staleResult, onSelectBuilding, onSelectRoom)).toBe(false)
    expect(onSelectBuilding).not.toHaveBeenCalled()
    expect(onSelectRoom).not.toHaveBeenCalled()
  })

  it("uses the map translation namespace and exposes the combobox contract", () => {
    render(<MapSearchBar {...baseProps} />)

    const input = screen.getByRole("combobox")
    expect(translation.useTranslation).toHaveBeenCalledWith("map")
    expect(input).toHaveAccessibleName("search.ariaLabel")
    expect(input).toHaveAttribute("placeholder", "search.placeholder")
    expect(input).toHaveAttribute("aria-expanded", "false")
    expect(input).toHaveAttribute("aria-controls", expect.stringMatching(/-listbox$/))
  })

  it("renders the search combobox", () => {
    render(<MapSearchBar {...baseProps} />)
    expect(screen.getByRole("combobox")).toBeInTheDocument()
  })

  it("renders no dropdown for an empty query", () => {
    render(<MapSearchBar {...baseProps} />)
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
  })

  it("opens a listbox with a matching building option when typing", async () => {
    const user = userEvent.setup()
    render(<MapSearchBar {...baseProps} />)
    await user.type(screen.getByRole("combobox"), "Главный")
    expect(screen.getByRole("listbox")).toBeInTheDocument()
    expect(screen.getByRole("option", { name: /Главный учебный корпус/ })).toBeInTheDocument()
  })

  it("normalizes whitespace and case for names and building letters", () => {
    const { rerender } = render(<MapSearchBar {...baseProps} />)
    const input = screen.getByRole("combobox")

    fireEvent.change(input, { target: { value: "  ГЛАВНЫЙ  " } })
    expect(screen.getByRole("option", { name: /Главный учебный корпус/ })).toHaveTextContent(
      'tooltip.floors|{"count":1}'
    )

    rerender(<MapSearchBar {...baseProps} />)
    const rerenderedInput = screen.getByRole("combobox")
    fireEvent.change(rerenderedInput, { target: { value: "гук" } })
    expect(screen.getByRole("option", { name: /Главный учебный корпус/ })).toBeInTheDocument()
  })

  it("does not return a building for a non-matching query", () => {
    render(<MapSearchBar {...baseProps} />)
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "unknown building" } })
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
  })

  it("fires onSelectBuilding when a building option is clicked", async () => {
    const user = userEvent.setup()
    const onSelectBuilding = vi.fn()
    render(<MapSearchBar {...baseProps} onSelectBuilding={onSelectBuilding} />)
    await user.type(screen.getByRole("combobox"), "Главный")
    await user.click(screen.getByRole("option", { name: /Главный учебный корпус/ }))
    expect(onSelectBuilding).toHaveBeenCalledWith("ГУК")
  })

  it("selects a matching room and renders its sublabel", async () => {
    const user = userEvent.setup()
    const onSelectRoom = vi.fn()
    render(<MapSearchBar {...baseProps} onSelectRoom={onSelectRoom} />)
    await user.type(screen.getByRole("combobox"), "101")

    const roomOption = screen.getByRole("option", { name: /ГУК-101.*Большая аудитория/ })
    expect(roomOption).toBeInTheDocument()
    fireEvent.pointerEnter(roomOption)
    expect(roomOption).toHaveAttribute("aria-selected", "true")
    await user.click(roomOption)

    expect(onSelectRoom).toHaveBeenCalledWith("ГУК", 1, "ГУК-101")
    expect(screen.getByRole("combobox")).toHaveValue("")
  })

  it("matches a room by its optional display name", () => {
    render(<MapSearchBar {...baseProps} />)
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "БОЛЬШАЯ" } })
    expect(screen.getByRole("option", { name: /ГУК-101.*Большая аудитория/ })).toBeInTheDocument()
  })

  it("does not treat the fallback room name as searchable content", () => {
    render(<MapSearchBar {...baseProps} />)
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "tryker" } })
    expect(screen.queryByRole("option")).not.toBeInTheDocument()
  })

  it("caps the combined result list at twelve options", () => {
    render(<MapSearchBar {...baseProps} buildings={[MANY_ROOM_BUILDING]} />)
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "room" } })
    expect(screen.getAllByRole("option")).toHaveLength(12)
  })

  it("handles a room without an optional display name", async () => {
    const user = userEvent.setup()
    const onSelectRoom = vi.fn()
    render(<MapSearchBar {...baseProps} onSelectRoom={onSelectRoom} />)
    await user.type(screen.getByRole("combobox"), "102")

    const roomOption = screen.getByRole("option", { name: "ГУК-102" })
    expect(roomOption).toBeInTheDocument()
    await user.click(roomOption)
    expect(onSelectRoom).toHaveBeenCalledWith("ГУК", 1, "ГУК-102")
  })

  it("selects a valid room on floor zero", async () => {
    const user = userEvent.setup()
    const onSelectRoom = vi.fn()
    const basementBuilding: CampusBuilding = {
      ...BUILDING,
      floors: [{ floor: 0, rooms: [{ id: "ГУК-B01", number: "B01", type: "seminar" }] }],
    }
    render(
      <MapSearchBar {...baseProps} buildings={[basementBuilding]} onSelectRoom={onSelectRoom} />
    )

    await user.type(screen.getByRole("combobox"), "B01")
    await user.click(screen.getByRole("option", { name: "ГУК-B01" }))

    expect(onSelectRoom).toHaveBeenCalledWith("ГУК", 0, "ГУК-B01")
  })

  it("clears a query through the clear button after input blur", async () => {
    const user = userEvent.setup()
    render(<MapSearchBar {...baseProps} />)
    const input = screen.getByRole("combobox")
    await user.type(input, "Главный")
    await user.click(screen.getByRole("button", { name: "search.clear" }))

    expect(input).toHaveValue("")
    expect(input).toHaveFocus()
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
  })

  it("supports keyboard selection and Escape dismissal", async () => {
    const user = userEvent.setup()
    const onSelectBuilding = vi.fn()
    render(<MapSearchBar {...baseProps} onSelectBuilding={onSelectBuilding} />)
    const input = screen.getByRole("combobox")

    await user.type(input, "Главный")
    await user.keyboard("{ArrowDown}{Enter}")
    expect(onSelectBuilding).toHaveBeenCalledWith("ГУК")

    await user.type(input, "ГУК")
    await user.keyboard("{ArrowDown}{ArrowUp}{Escape}")
    expect(input).toHaveValue("")
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
  })

  it("selects the active option by its global index and blurs the input", () => {
    const onSelectRoom = vi.fn()
    render(<MapSearchBar {...baseProps} onSelectRoom={onSelectRoom} />)
    const input = screen.getByRole("combobox")

    fireEvent.change(input, { target: { value: "ГУК" } })
    fireEvent.keyDown(input, { key: "ArrowDown" })
    fireEvent.keyDown(input, { key: "ArrowDown" })
    fireEvent.keyDown(input, { key: "Enter" })

    expect(onSelectRoom).toHaveBeenCalledWith("ГУК", 1, "ГУК-101")
    expect(input).not.toHaveFocus()
    expect(input).toHaveValue("")
  })

  it("moves the active option with bounded ArrowDown and ArrowUp navigation", () => {
    const thirdBuilding = {
      ...CAMPUS_BUILDINGS[0]!,
      letter: "ЦИТ" as const,
      name: "Campus Lab",
    } satisfies CampusBuilding
    render(<MapSearchBar {...baseProps} buildings={[...CAMPUS_BUILDINGS, thirdBuilding]} />)
    const input = screen.getByRole("combobox")
    fireEvent.change(input, { target: { value: "Campus" } })
    const options = screen.getAllByRole("option")

    expect(input).not.toHaveAttribute("aria-activedescendant")

    fireEvent.keyDown(input, { key: "ArrowUp" })
    expect(options[0]).toHaveAttribute("aria-selected", "true")

    fireEvent.keyDown(input, { key: "ArrowDown" })
    expect(options[1]).toHaveAttribute("aria-selected", "true")
    expect(input).toHaveAttribute("aria-activedescendant", options[1]!.id)

    fireEvent.keyDown(input, { key: "ArrowDown" })
    expect(options[2]).toHaveAttribute("aria-selected", "true")
    fireEvent.keyDown(input, { key: "ArrowDown" })
    expect(options[2]).toHaveAttribute("aria-selected", "true")

    fireEvent.keyDown(input, { key: "ArrowUp" })
    expect(options[1]).toHaveAttribute("aria-selected", "true")
    fireEvent.keyDown(input, { key: "ArrowUp" })
    expect(options[0]).toHaveAttribute("aria-selected", "true")
  })

  it("ignores keyboard navigation after the listbox closes or when there are no results", () => {
    vi.useFakeTimers()
    try {
      render(<MapSearchBar {...baseProps} buildings={CAMPUS_BUILDINGS} />)
      const input = screen.getByRole("combobox")
      fireEvent.change(input, { target: { value: "Campus" } })
      fireEvent.blur(input)
      act(() => vi.advanceTimersByTime(200))
      fireEvent.keyDown(input, { key: "ArrowDown" })
      expect(input).not.toHaveAttribute("aria-activedescendant")

      fireEvent.change(input, { target: { value: "   " } })
      fireEvent.keyDown(input, { key: "ArrowDown" })
      fireEvent.keyDown(input, { key: "ArrowUp" })
      expect(input).not.toHaveAttribute("aria-activedescendant")
    } finally {
      vi.useRealTimers()
    }
  })

  it("keeps aria-expanded and aria-activedescendant synchronized with results", () => {
    render(<MapSearchBar {...baseProps} buildings={CAMPUS_BUILDINGS} />)
    const input = screen.getByRole("combobox")

    fireEvent.change(input, { target: { value: "Campus" } })
    const listbox = screen.getByRole("listbox")
    expect(input).toHaveAttribute("aria-expanded", "true")
    expect(input).toHaveAttribute("aria-controls", listbox.id)
    expect(input).not.toHaveAttribute("aria-activedescendant")

    const firstOption = screen.getAllByRole("option")[0]!
    fireEvent.keyDown(input, { key: "ArrowDown" })
    expect(input).toHaveAttribute("aria-activedescendant", firstOption.id)

    fireEvent.change(input, { target: { value: "no such place" } })
    expect(input).toHaveAttribute("aria-expanded", "false")
    expect(input).not.toHaveAttribute("aria-activedescendant")
  })

  it("ignores Enter until a search result is active", () => {
    const onSelectBuilding = vi.fn()
    render(<MapSearchBar {...baseProps} onSelectBuilding={onSelectBuilding} />)
    const input = screen.getByRole("combobox")

    fireEvent.change(input, { target: { value: "Главный" } })
    fireEvent.keyDown(input, { key: "Enter" })

    expect(onSelectBuilding).not.toHaveBeenCalled()
  })

  it("closes the dropdown after the blur delay", () => {
    vi.useFakeTimers()
    try {
      render(<MapSearchBar {...baseProps} />)
      const input = screen.getByRole("combobox")
      fireEvent.change(input, { target: { value: "Главный" } })
      fireEvent.blur(input)

      act(() => vi.advanceTimersByTime(200))
      expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it("reopens a closed dropdown when focus returns to a non-empty query", () => {
    vi.useFakeTimers()
    try {
      render(<MapSearchBar {...baseProps} />)
      const input = screen.getByRole("combobox")
      fireEvent.change(input, { target: { value: "Главный" } })
      fireEvent.blur(input)
      act(() => vi.advanceTimersByTime(200))
      expect(screen.queryByRole("listbox")).not.toBeInTheDocument()

      fireEvent.focus(input)
      expect(screen.getByRole("listbox")).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it("clears directly when no blur timer is pending", () => {
    render(<MapSearchBar {...baseProps} />)
    const input = screen.getByRole("combobox")
    fireEvent.change(input, { target: { value: "Главный" } })

    fireEvent.click(screen.getByRole("button", { name: "search.clear" }))

    expect(input).toHaveValue("")
  })

  it("cancels a pending blur timer when selecting a result", () => {
    vi.useFakeTimers()
    const clearTimeoutSpy = vi.spyOn(window, "clearTimeout")
    try {
      render(<MapSearchBar {...baseProps} />)
      const input = screen.getByRole("combobox")
      fireEvent.change(input, { target: { value: "Главный" } })
      const option = screen.getByRole("option", { name: /Главный учебный корпус/ })

      fireEvent.blur(input)
      fireEvent.click(option)

      expect(clearTimeoutSpy).toHaveBeenCalledTimes(1)
    } finally {
      clearTimeoutSpy.mockRestore()
      vi.useRealTimers()
    }
  })

  it("cancels a pending blur timer when clearing the query", () => {
    vi.useFakeTimers()
    const clearTimeoutSpy = vi.spyOn(window, "clearTimeout")
    try {
      render(<MapSearchBar {...baseProps} />)
      const input = screen.getByRole("combobox")
      fireEvent.change(input, { target: { value: "Главный" } })
      fireEvent.blur(input)
      fireEvent.click(screen.getByRole("button", { name: "search.clear" }))
      expect(clearTimeoutSpy).toHaveBeenCalledTimes(1)
    } finally {
      clearTimeoutSpy.mockRestore()
      vi.useRealTimers()
    }
  })

  it("does not clear a timeout when clearing without a pending blur", () => {
    const clearTimeoutSpy = vi.spyOn(window, "clearTimeout")
    try {
      render(<MapSearchBar {...baseProps} />)
      const input = screen.getByRole("combobox")
      fireEvent.change(input, { target: { value: "Главный" } })
      fireEvent.click(screen.getByRole("button", { name: "search.clear" }))
      expect(clearTimeoutSpy).not.toHaveBeenCalled()
    } finally {
      clearTimeoutSpy.mockRestore()
    }
  })

  it("does not clear a timeout when selecting without a pending blur", () => {
    const clearTimeoutSpy = vi.spyOn(window, "clearTimeout")
    try {
      render(<MapSearchBar {...baseProps} />)
      const input = screen.getByRole("combobox")
      fireEvent.change(input, { target: { value: "Главный" } })
      fireEvent.click(screen.getByRole("option", { name: /Главный учебный корпус/ }))
      expect(clearTimeoutSpy).not.toHaveBeenCalled()
    } finally {
      clearTimeoutSpy.mockRestore()
    }
  })

  it("skips only the blur immediately following a selection", () => {
    vi.useFakeTimers()
    const setTimeoutSpy = vi.spyOn(window, "setTimeout")
    try {
      render(<MapSearchBar {...baseProps} />)
      const input = screen.getByRole("combobox")
      fireEvent.change(input, { target: { value: "Главный" } })
      fireEvent.click(screen.getByRole("option", { name: /Главный учебный корпус/ }))

      setTimeoutSpy.mockClear()
      fireEvent.blur(input)
      expect(setTimeoutSpy).not.toHaveBeenCalled()
      fireEvent.blur(input)
      expect(setTimeoutSpy).toHaveBeenCalledTimes(1)
    } finally {
      setTimeoutSpy.mockRestore()
      vi.useRealTimers()
    }
  })

  it("cancels a pending blur close when unmounted", () => {
    const clearTimeoutSpy = vi.spyOn(window, "clearTimeout")
    const view = render(<MapSearchBar {...baseProps} />)
    fireEvent.blur(screen.getByRole("combobox"))

    view.unmount()

    expect(clearTimeoutSpy).toHaveBeenCalledOnce()
    clearTimeoutSpy.mockRestore()
  })

  it("does not call clearTimeout when unmounted without a pending blur", () => {
    const clearTimeoutSpy = vi.spyOn(window, "clearTimeout")
    const view = render(<MapSearchBar {...baseProps} />)
    view.unmount()
    expect(clearTimeoutSpy).not.toHaveBeenCalled()
    clearTimeoutSpy.mockRestore()
  })

  it("exposes the committed input through the optional imperative ref", () => {
    const searchInputRef: { current: HTMLInputElement | null } = { current: null }
    render(<MapSearchBar {...baseProps} searchInputRef={searchInputRef} />)
    const input = screen.getByRole("combobox")
    expect(searchInputRef.current).toBe(input)
    searchInputRef.current?.focus()
    expect(input).toHaveFocus()
  })

  it("rebinds the imperative handle when a parent swaps ref objects", () => {
    const firstRef: { current: HTMLInputElement | null } = { current: null }
    const secondRef: { current: HTMLInputElement | null } = { current: null }
    const view = render(<MapSearchBar {...baseProps} searchInputRef={firstRef} />)
    const input = screen.getByRole("combobox")

    view.rerender(<MapSearchBar {...baseProps} searchInputRef={secondRef} />)

    expect(firstRef.current).toBeNull()
    expect(secondRef.current).toBe(input)
  })

  it("uses the latest selection callbacks after rerender", () => {
    const firstCallback = vi.fn()
    const latestCallback = vi.fn()
    const view = render(<MapSearchBar {...baseProps} onSelectBuilding={firstCallback} />)
    view.rerender(<MapSearchBar {...baseProps} onSelectBuilding={latestCallback} />)

    const input = screen.getByRole("combobox")
    fireEvent.change(input, { target: { value: "Главный" } })
    fireEvent.click(screen.getByRole("option", { name: /Главный учебный корпус/ }))

    expect(firstCallback).not.toHaveBeenCalled()
    expect(latestCallback).toHaveBeenCalledWith("ГУК")
  })

  it("renders each result group only when it has matching options", () => {
    const { rerender } = render(<MapSearchBar {...baseProps} />)
    const input = screen.getByRole("combobox")

    fireEvent.change(input, { target: { value: "Главный" } })
    expect(screen.getByText("search.groupBuildings")).toBeInTheDocument()
    expect(screen.queryByText("search.groupRooms")).not.toBeInTheDocument()

    rerender(<MapSearchBar {...baseProps} />)
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "101" } })
    expect(screen.getByText("search.groupRooms")).toBeInTheDocument()
    expect(screen.queryByText("search.groupBuildings")).not.toBeInTheDocument()
  })

  it("keeps room option indexes and ids global across building and room groups", () => {
    render(<MapSearchBar {...baseProps} />)
    const input = screen.getByRole("combobox")
    fireEvent.change(input, { target: { value: "ГУК" } })

    expect(screen.getByText("search.groupBuildings")).toBeInTheDocument()
    expect(screen.getByText("search.groupRooms")).toBeInTheDocument()
    const options = screen.getAllByRole("option")
    expect(options).toHaveLength(3)
    expect(options.every((option) => option.getAttribute("aria-selected") === "false")).toBe(true)
    expect(new Set(options.map((option) => option.id)).size).toBe(3)
    expect(options.map((option) => option.id)).toEqual(
      expect.arrayContaining([expect.stringMatching(/-opt-0$/), expect.stringMatching(/-opt-1$/)])
    )

    const roomOption = screen.getByRole("option", { name: /ГУК-101.*Большая аудитория/ })
    fireEvent.pointerEnter(roomOption)
    expect(input).toHaveAttribute("aria-activedescendant", roomOption.id)
    expect(roomOption).toHaveAttribute("aria-selected", "true")
    expect(options.find((option) => option !== roomOption)).toHaveAttribute(
      "aria-selected",
      "false"
    )
  })

  it("applies the active style only to the option under keyboard or pointer focus", () => {
    render(<MapSearchBar {...baseProps} buildings={CAMPUS_BUILDINGS} />)
    const input = screen.getByRole("combobox")
    fireEvent.change(input, { target: { value: "Campus" } })
    const options = screen.getAllByRole("option")

    fireEvent.keyDown(input, { key: "ArrowDown" })
    expect(options[0]).toHaveStyle({ backgroundColor: "var(--bg-surface-hover)" })
    expect(options[1]).not.toHaveStyle({ backgroundColor: "var(--bg-surface-hover)" })
    expect(options[0]).toHaveAttribute("aria-selected", "true")
    expect(options[1]).toHaveAttribute("aria-selected", "false")

    fireEvent.pointerEnter(options[1]!)
    expect(options[0]).not.toHaveStyle({ backgroundColor: "var(--bg-surface-hover)" })
    expect(options[1]).toHaveStyle({ backgroundColor: "var(--bg-surface-hover)" })
    expect(options[0]).toHaveAttribute("aria-selected", "false")
    expect(options[1]).toHaveAttribute("aria-selected", "true")
  })

  it("applies the active style to room options as well as building options", () => {
    render(<MapSearchBar {...baseProps} />)
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "ГУК" } })
    const roomOptions = screen
      .getAllByRole("option")
      .filter((option) => option.textContent?.startsWith("ГУК-"))
    expect(roomOptions).toHaveLength(2)

    fireEvent.pointerEnter(roomOptions[0]!)
    expect(roomOptions[0]).toHaveStyle({ backgroundColor: "var(--bg-surface-hover)" })
    expect(roomOptions[1]).not.toHaveStyle({ backgroundColor: "var(--bg-surface-hover)" })
    expect(roomOptions[0]).toHaveAttribute("aria-selected", "true")
    expect(roomOptions[1]).toHaveAttribute("aria-selected", "false")

    fireEvent.pointerEnter(roomOptions[1]!)
    expect(roomOptions[0]).not.toHaveStyle({ backgroundColor: "var(--bg-surface-hover)" })
    expect(roomOptions[1]).toHaveStyle({ backgroundColor: "var(--bg-surface-hover)" })
    expect(roomOptions[0]).toHaveAttribute("aria-selected", "false")
    expect(roomOptions[1]).toHaveAttribute("aria-selected", "true")
  })

  it("omits empty room and building sublabels instead of rendering empty spans", () => {
    const roomView = render(<MapSearchBar {...baseProps} />)
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "102" } })
    const roomOption = screen.getByRole("option", { name: "ГУК-102" })
    expect(roomOption.querySelector("span.text-xs")).not.toBeInTheDocument()
    roomView.unmount()

    translation.t.mockImplementation((key) => (key === "tooltip.floors" ? "" : key))
    render(<MapSearchBar {...baseProps} />)
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "Главный" } })
    const buildingOption = screen.getByRole("option", { name: "Главный учебный корпус" })
    expect(buildingOption.querySelector("span.text-xs")).not.toBeInTheDocument()
  })
})
