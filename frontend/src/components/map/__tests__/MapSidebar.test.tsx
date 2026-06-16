import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi } from "vitest"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))
vi.mock("@/contexts/AppShellContext", () => ({
  useAppShell: () => ({ setOverlayState: vi.fn() }),
}))

import { MapSidebar } from "@/components/map/MapSidebar"
import type { CampusBuilding, BuildingFloor } from "@/data/campusBuildings"

const FLOOR_1: BuildingFloor = {
  floor: 1,
  rooms: [
    { id: "ГУК-101", number: "101", type: "lecture", capacity: 120, name: "Большая аудитория" },
  ],
}
const FLOOR_2: BuildingFloor = {
  floor: 2,
  rooms: [{ id: "ГУК-201", number: "201", type: "seminar" }],
}

const BUILDING: CampusBuilding = {
  letter: "ГУК",
  structureId: "стр. 8",
  name: "Главный учебный корпус",
  description: "Главное здание университета.",
  address: "Рязанский проспект, 99",
  hours: { weekday: "08:00–22:00", saturday: "09:00–20:00", sunday: "Закрыто" },
  amenities: ["Wi-Fi", "Буфет"],
  tags: ["study"],
  colorVar: "var(--color-blue-500)",
  colorHex: "#3b82f6",
  floorCount: 2,
  floors: [FLOOR_1, FLOOR_2],
  geoCoords: [55.71, 37.81],
}

const baseProps = {
  building: BUILDING,
  floor: FLOOR_1,
  selectedFloor: 1,
  selectedRoom: null,
  onFloorChange: vi.fn(),
  onRoomClick: vi.fn(),
  onClose: vi.fn(),
  isMobile: false,
}

describe("MapSidebar", () => {
  it("renders nothing when no building is selected", () => {
    const { container } = render(
      <MapSidebar {...baseProps} building={undefined} floor={undefined} />
    )
    expect(container).toBeEmptyDOMElement()
  })

  it("renders the building header, address, and description", () => {
    render(<MapSidebar {...baseProps} />)
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("Главный учебный корпус")
    expect(screen.getByText("Рязанский проспект, 99")).toBeInTheDocument()
    expect(screen.getByText("Главное здание университета.")).toBeInTheDocument()
  })

  it("renders a floor selector radiogroup with one radio per floor", () => {
    render(<MapSidebar {...baseProps} />)
    expect(screen.getByRole("radiogroup")).toBeInTheDocument()
    expect(screen.getAllByRole("radio")).toHaveLength(2)
  })

  it("fires onFloorChange when a floor radio is clicked", async () => {
    const user = userEvent.setup()
    const onFloorChange = vi.fn()
    render(<MapSidebar {...baseProps} onFloorChange={onFloorChange} />)
    await user.click(screen.getByRole("radio", { name: "2" }))
    expect(onFloorChange).toHaveBeenCalledWith(2)
  })

  it("fires onRoomClick when a room button is clicked", async () => {
    const user = userEvent.setup()
    const onRoomClick = vi.fn()
    render(<MapSidebar {...baseProps} onRoomClick={onRoomClick} />)
    await user.click(screen.getByRole("button", { name: /ГУК-101/ }))
    expect(onRoomClick).toHaveBeenCalledWith("ГУК-101")
  })

  it("fires onClose from the desktop close button", async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<MapSidebar {...baseProps} onClose={onClose} />)
    await user.click(screen.getByRole("button", { name: "sidebar.close" }))
    expect(onClose).toHaveBeenCalledOnce()
  })
})
