import { fireEvent, render, screen, act } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts && Object.keys(opts).length ? `${key}:${JSON.stringify(opts)}` : key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))
vi.mock("@/contexts/AppShellContext", () => ({
  useAppShell: () => ({ setOverlayState: vi.fn() }),
}))

const hooks = vi.hoisted(() => ({
  open: true,
  roomStatus: null as { status: "free" | "busy"; busyUntil?: string } | null,
}))

vi.mock("@/utils/buildingHours", () => ({
  isOpenNow: () => hooks.open,
}))
vi.mock("@/utils/roomStatus", () => ({
  getRoomStatus: () => hooks.roomStatus,
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

describe("MapSidebar branches", () => {
  beforeEach(() => {
    hooks.open = true
    hooks.roomStatus = null
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.runOnlyPendingTimers()
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it("renders the mobile bottom sheet branch (role=dialog, drag handle, sheetReady timer)", () => {
    render(<MapSidebar {...baseProps} isMobile />)
    const dialog = screen.getByRole("dialog")
    expect(dialog).toHaveAttribute("aria-modal", "true")
    expect(dialog).toHaveAttribute("aria-label", "Главный учебный корпус")
    expect(screen.getByLabelText("sidebar.dragToResize")).toBeInTheDocument()
    // No desktop close button in the mobile branch
    expect(screen.queryByRole("button", { name: "sidebar.close" })).not.toBeInTheDocument()
    // Advance past the 260ms sheetReady entrance timer (overflow-hidden → overflow-y-auto)
    act(() => {
      vi.advanceTimersByTime(300)
    })
  })

  it("tracks mobile pointer drag and ignores move/up events before dragging", () => {
    render(<MapSidebar {...baseProps} isMobile />)
    const handle = screen.getByLabelText("sidebar.dragToResize")
    const setPointerCapture = vi.fn()
    const releasePointerCapture = vi.fn()
    Object.defineProperty(handle, "setPointerCapture", { value: setPointerCapture })
    Object.defineProperty(handle, "releasePointerCapture", { value: releasePointerCapture })

    fireEvent.pointerMove(handle, { pointerId: 7, clientY: 420 })
    fireEvent.pointerUp(handle, { pointerId: 7, clientY: 420 })
    fireEvent.pointerDown(handle, { pointerId: 7, clientY: 520 })
    fireEvent.pointerMove(handle, { pointerId: 7, clientY: 240 })
    fireEvent.pointerUp(handle, { pointerId: 7, clientY: 240 })
    fireEvent.pointerDown(handle, { pointerId: 8, clientY: 240 })
    fireEvent.pointerMove(handle, { pointerId: 8, clientY: 800 })
    fireEvent.pointerUp(handle, { pointerId: 8, clientY: 800 })

    expect(setPointerCapture).toHaveBeenCalledWith(7)
    expect(releasePointerCapture).toHaveBeenCalledWith(7)
  })

  it("renders the amenities section when building.amenities is non-empty", () => {
    render(<MapSidebar {...baseProps} />)
    expect(screen.getByText("sidebar.amenities")).toBeInTheDocument()
    expect(screen.getByText("Wi-Fi")).toBeInTheDocument()
    expect(screen.getByText("Буфет")).toBeInTheDocument()
  })

  it("omits the amenities section when building.amenities is empty", () => {
    render(<MapSidebar {...baseProps} building={{ ...BUILDING, amenities: [] }} />)
    expect(screen.queryByText("sidebar.amenities")).not.toBeInTheDocument()
  })

  it("renders the selected-room detail panel with type and capacity", () => {
    render(<MapSidebar {...baseProps} selectedRoom="ГУК-101" />)
    // roomTypes.<type> label rendered from the detail panel
    expect(screen.getByText("roomTypes.lecture")).toBeInTheDocument()
    // capacity value (120) shown alongside Users icon
    expect(screen.getByText("120")).toBeInTheDocument()
    // room name appears in both the list item and the detail panel
    expect(screen.getAllByText("Большая аудитория").length).toBeGreaterThan(0)
  })

  it("renders a free room-status badge when getRoomStatus returns free", () => {
    hooks.roomStatus = { status: "free" }
    render(<MapSidebar {...baseProps} todayLessons={[{ room: "101", start_time: "10:00" }]} />)
    expect(screen.getByText("sidebar.roomFree")).toBeInTheDocument()
  })

  it("renders a busy room-status badge with interpolated time when getRoomStatus returns busy", () => {
    hooks.roomStatus = { status: "busy", busyUntil: "11:30" }
    render(<MapSidebar {...baseProps} todayLessons={[{ room: "101", start_time: "10:00" }]} />)
    expect(screen.getByText(/sidebar\.roomBusy/)).toBeInTheDocument()
  })

  it("renders the building photo as an img when building.photo is present", () => {
    render(<MapSidebar {...baseProps} building={{ ...BUILDING, photo: "https://x/photo.jpg" }} />)
    const img = screen.getByRole("img", { name: "Главный учебный корпус" })
    expect(img).toHaveAttribute("src", "https://x/photo.jpg")
  })

  it("renders the gradient placeholder (no img) when building.photo is absent", () => {
    render(<MapSidebar {...baseProps} />)
    expect(screen.queryByRole("img", { name: "Главный учебный корпус" })).not.toBeInTheDocument()
  })

  it("renders the open-now hours badge when isOpenNow is true", () => {
    hooks.open = true
    render(<MapSidebar {...baseProps} />)
    expect(screen.getByText("hours.openNow")).toBeInTheDocument()
  })

  it("renders the closed-now hours badge when isOpenNow is false", () => {
    hooks.open = false
    render(<MapSidebar {...baseProps} />)
    expect(screen.getByText("hours.closedNow")).toBeInTheDocument()
  })
})
