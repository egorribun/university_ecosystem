import { render, screen } from "@testing-library/react"
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
  floors: [{ floor: 1, rooms: [{ id: "ГУК-101", number: "101", type: "lecture" }] }],
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
})
