import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi } from "vitest"
import type { ReactNode } from "react"

vi.mock("react-map-gl/maplibre", async () => {
  const base = (await import("@/tests/helpers/mapGlMock")).mapGlMock()
  return {
    ...base,
    Popup: ({ children, onClose }: { children?: ReactNode; onClose?: () => void }) => (
      <div>
        {children}
        <button type="button" onClick={() => onClose?.()}>
          close-popup
        </button>
      </div>
    ),
  }
})
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))
vi.mock("@/utils/buildingHours", () => ({
  isOpenNow: (hours: { weekday: string }) => hours.weekday === "open",
}))

import { BuildingMarker } from "@/components/map/BuildingMarker"
import type { CampusBuilding } from "@/data/campusBuildings"

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
  floorCount: 8,
  floors: [{ floor: 1, rooms: [{ id: "ГУК-101", number: "101", type: "lecture" }] }],
  geoCoords: [55.71, 37.81],
}

const baseProps = {
  building: BUILDING,
  isSelected: false,
  isHighlighted: false,
  onClick: vi.fn(),
}

describe("BuildingMarker", () => {
  it("renders the building pin with an accessible label", () => {
    render(<BuildingMarker {...baseProps} />)
    expect(screen.getByRole("button", { name: "a11y.buildingSelected" })).toBeInTheDocument()
  })

  it("fires onClick with the building letter when the pin is clicked", async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()
    render(<BuildingMarker {...baseProps} onClick={onClick} />)
    await user.click(screen.getByRole("button", { name: "a11y.buildingSelected" }))
    expect(onClick).toHaveBeenCalledWith("ГУК")
  })

  it("renders the detail popup when the popup is open", () => {
    render(<BuildingMarker {...baseProps} isPopupOpen />)
    expect(screen.getByText("Главный учебный корпус")).toBeInTheDocument()
    expect(screen.getByText("стр. 8")).toBeInTheDocument()
  })

  it("renders an event badge when eventCount is positive", () => {
    render(<BuildingMarker {...baseProps} eventCount={3} />)
    expect(screen.getByText("3")).toBeInTheDocument()
  })

  it("covers active/highlighted states and keyboard activation", async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()
    const onPopupOpen = vi.fn()
    const { unmount } = render(
      <BuildingMarker {...baseProps} isHighlighted onClick={onClick} onPopupOpen={onPopupOpen} />
    )
    const highlighted = screen.getByRole("button", { name: "a11y.buildingSelected" })
    expect(highlighted).toHaveClass("map-building-pin--pulse")
    await user.click(highlighted)
    highlighted.focus()
    await user.keyboard("{Enter}")
    await user.keyboard(" ")
    expect(onClick).toHaveBeenCalledTimes(3)
    expect(onPopupOpen).toHaveBeenCalledTimes(3)
    fireEvent.keyDown(highlighted, { key: "Tab" })
    expect(onClick).toHaveBeenCalledTimes(3)
    unmount()

    render(<BuildingMarker {...baseProps} isSelected isHighlighted />)
    const active = screen.getByRole("button", { name: "a11y.buildingSelected" })
    expect(active).toHaveClass("map-building-pin--active")
    expect(active).not.toHaveClass("map-building-pin--pulse")
    expect(active).toHaveStyle({ minWidth: "44px", minHeight: "44px" })
  })

  it("renders a photo popup and open-hours styling", () => {
    const onPopupClose = vi.fn()
    render(
      <BuildingMarker
        {...baseProps}
        isSelected
        isPopupOpen
        onPopupClose={onPopupClose}
        eventCount={0}
        building={{
          ...BUILDING,
          photo: "/campus.jpg",
          hours: { ...BUILDING.hours, weekday: "open" },
        }}
      />
    )
    expect(screen.getByRole("img", { name: BUILDING.name })).toHaveAttribute("src", "/campus.jpg")
    expect(screen.getByText("hours.openNow")).toBeInTheDocument()
    expect(screen.queryByText("0")).not.toBeInTheDocument()
    screen.getByRole("button", { name: "close-popup" }).click()
    expect(onPopupClose).toHaveBeenCalledOnce()
  })
})
