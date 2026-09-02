import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, it, expect, vi } from "vitest"
import type { ReactNode } from "react"

const markerMocks = vi.hoisted(() => {
  const translationCalls: Array<{ key: string; options?: Record<string, unknown> }> = []
  const useTranslation = vi.fn(() => ({
    t: (key: string, options?: Record<string, unknown>) => {
      translationCalls.push({ key, options })
      return key
    },
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }))

  return {
    popupProps: [] as Array<Record<string, unknown>>,
    translationCalls,
    useTranslation,
  }
})

vi.mock("react-map-gl/maplibre", async () => {
  const base = (await import("@/tests/helpers/mapGlMock")).mapGlMock()
  return {
    ...base,
    Popup: ({ children, onClose, ...props }: { children?: ReactNode; onClose?: () => void }) => {
      markerMocks.popupProps.push(props)
      return (
        <div>
          {children}
          <button type="button" onClick={() => onClose?.()}>
            close-popup
          </button>
        </div>
      )
    },
  }
})
vi.mock("react-i18next", () => ({
  useTranslation: markerMocks.useTranslation,
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
  beforeEach(() => {
    markerMocks.popupProps.length = 0
    markerMocks.translationCalls.length = 0
    markerMocks.useTranslation.mockClear()
  })

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

  it("keeps pin geometry, base classes, and translated counts observable", () => {
    const building = {
      ...BUILDING,
      floors: [
        BUILDING.floors[0]!,
        { floor: 2, rooms: [{ id: "ГУК-201", number: "201", type: "seminar" as const }] },
      ],
    }

    render(<BuildingMarker {...baseProps} building={building} index={3} eventCount={2} />)

    const pin = screen.getByRole("button", { name: "a11y.buildingSelected" })
    expect(pin).toHaveClass("map-building-pin--entering")
    expect(pin).toHaveStyle({
      minWidth: "44px",
      minHeight: "44px",
      "--stagger-index": "3",
      "--_pin-color": BUILDING.colorHex,
    })
    expect(markerMocks.useTranslation).toHaveBeenCalledWith("map")

    expect(
      markerMocks.translationCalls.find(({ key }) => key === "a11y.buildingSelected")?.options
    ).toEqual({ name: BUILDING.name, floors: BUILDING.floorCount, rooms: 2 })

    const badge = screen.getByText("2")
    expect(badge).toHaveClass("map-event-badge")
    expect(badge).toHaveAttribute("aria-label", "events.badgeLabel")
    expect(
      markerMocks.translationCalls.find(({ key }) => key === "events.badgeLabel")?.options
    ).toEqual({ count: 2 })
  })

  it("renders popup metadata, status styles, and at most four amenity chips", () => {
    const amenities = ["Wi-Fi", "Cafe", "Library", "Labs", "Overflow"]
    render(
      <BuildingMarker
        {...baseProps}
        isSelected
        isPopupOpen
        building={{
          ...BUILDING,
          amenities,
          description: "Open building",
          hours: { ...BUILDING.hours, weekday: "open" },
        }}
      />
    )

    const placeholder = document.querySelector(".map-photo-placeholder")
    expect(placeholder).toHaveStyle({
      background: `linear-gradient(135deg, ${BUILDING.colorHex}, color-mix(in srgb, ${BUILDING.colorHex} 60%, black))`,
    })
    expect(screen.getByText("Open building")).toHaveClass("map-popup-desc")
    expect(screen.getByText("tooltip.floors")).toBeInTheDocument()
    expect(screen.getByText("sidebar.roomCount")).toBeInTheDocument()

    const status = screen.getByText("hours.openNow")
    expect(status).toHaveStyle({
      backgroundColor: "color-mix(in srgb, var(--color-emerald-500) 15%, transparent)",
      color: "var(--color-emerald-500)",
    })
    expect(document.querySelectorAll(".map-popup-chip")).toHaveLength(4)
    expect(screen.queryByText("Overflow")).not.toBeInTheDocument()

    expect(markerMocks.popupProps[0]).toMatchObject({
      closeButton: true,
      closeOnClick: false,
      className: "map-popup-premium",
      maxWidth: "280px",
    })
  })

  it("hides optional popup sections for sparse closed buildings", () => {
    render(
      <BuildingMarker
        {...baseProps}
        isPopupOpen
        building={{
          ...BUILDING,
          description: "",
          amenities: [],
          hours: { ...BUILDING.hours, weekday: "closed" },
        }}
      />
    )

    expect(document.querySelector(".map-popup-desc")).toBeNull()
    expect(document.querySelector(".map-popup-amenities")).toBeNull()
    const status = screen.getByText("hours.closedNow")
    expect(status).toHaveStyle({
      backgroundColor: "color-mix(in srgb, var(--color-rose-500) 15%, transparent)",
      color: "var(--color-rose-500)",
    })
    screen.getByRole("button", { name: "close-popup" }).click()
  })
})
