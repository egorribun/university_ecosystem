import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi } from "vitest"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

import { MapSearchBar } from "@/components/map/MapSearchBar"
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

describe("MapSearchBar", () => {
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

  it("cancels a pending blur close when unmounted", () => {
    const clearTimeoutSpy = vi.spyOn(window, "clearTimeout")
    const view = render(<MapSearchBar {...baseProps} />)
    fireEvent.blur(screen.getByRole("combobox"))

    view.unmount()

    expect(clearTimeoutSpy).toHaveBeenCalledOnce()
    clearTimeoutSpy.mockRestore()
  })
})
