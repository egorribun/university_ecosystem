import { fireEvent, render, screen, act } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts && Object.keys(opts).length ? `${key}:${JSON.stringify(opts)}` : key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))
const hooks = vi.hoisted(() => ({
  open: true,
  roomStatus: null as { status: "free" | "busy"; busyUntil?: string } | null,
  setOverlayState: vi.fn(),
}))

vi.mock("@/contexts/AppShellContext", () => ({
  useAppShell: () => ({ setOverlayState: hooks.setOverlayState }),
}))

vi.mock("@/utils/buildingHours", () => ({
  isOpenNow: () => hooks.open,
}))
vi.mock("@/utils/roomStatus", () => ({
  getRoomStatus: () => hooks.roomStatus,
}))

import { getViewportHeight, MapSidebar } from "@/components/map/MapSidebar"
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
    vi.unstubAllGlobals()
    vi.runOnlyPendingTimers()
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it("uses the server viewport fallback without a window", () => {
    vi.stubGlobal("window", undefined)
    expect(getViewportHeight()).toBe(800)
  })

  it("renders the mobile bottom sheet branch (role=dialog, drag handle, sheetReady timer)", () => {
    render(<MapSidebar {...baseProps} isMobile />)
    const dialog = screen.getByRole("dialog")
    expect(dialog).toHaveAttribute("aria-modal", "true")
    expect(dialog).toHaveAttribute("aria-labelledby")
    expect(dialog).toHaveAttribute("aria-describedby")
    expect(document.getElementById(dialog.getAttribute("aria-labelledby")!)).toHaveTextContent(
      "Главный учебный корпус"
    )
    expect(document.getElementById(dialog.getAttribute("aria-describedby")!)).toHaveTextContent(
      "Главное здание университета."
    )
    const handle = screen.getByRole("slider", { name: "sidebar.dragToResize" })
    expect(handle).toHaveAttribute("aria-orientation", "vertical")
    expect(handle).toHaveAttribute("tabindex", "0")
    expect(handle.className).toContain("min-h-[44px]")
    // No desktop close button in the mobile branch
    expect(screen.queryByRole("button", { name: "sidebar.close" })).not.toBeInTheDocument()
    // Advance past the 260ms sheetReady entrance timer (overflow-hidden → overflow-y-auto)
    act(() => {
      vi.advanceTimersByTime(300)
    })
    expect(dialog.querySelector(".overflow-y-auto")).toBeInTheDocument()
    expect(hooks.setOverlayState).toHaveBeenCalledWith("map-sidebar", {
      scrollLocked: true,
      blurred: false,
    })
  })

  it("cleans up the app-shell scroll lock when the mobile sheet closes", () => {
    const { unmount } = render(<MapSidebar {...baseProps} isMobile />)
    unmount()
    expect(hooks.setOverlayState).toHaveBeenLastCalledWith("map-sidebar", null)
  })

  it("supports keyboard resizing with bounded snap points", () => {
    render(<MapSidebar {...baseProps} isMobile />)
    const handle = screen.getByRole("slider", { name: "sidebar.dragToResize" })
    const maxHeight = Math.round(window.innerHeight * 0.9)
    expect(Number(handle.getAttribute("aria-valuemin"))).toBe(100)
    expect(Number(handle.getAttribute("aria-valuemax"))).toBe(maxHeight)

    fireEvent.keyDown(handle, { key: "ArrowDown" })
    expect(Number(handle.getAttribute("aria-valuenow"))).toBe(160)
    fireEvent.keyDown(handle, { key: "ArrowUp" })
    expect(Number(handle.getAttribute("aria-valuenow"))).toBe(Math.round(window.innerHeight * 0.5))
    fireEvent.keyDown(handle, { key: "End" })
    expect(Number(handle.getAttribute("aria-valuenow"))).toBe(Math.round(window.innerHeight * 0.85))
    fireEvent.keyDown(handle, { key: "Home" })
    expect(Number(handle.getAttribute("aria-valuenow"))).toBe(160)
  })

  it("ignores unrelated keyboard input without changing the sheet", () => {
    render(<MapSidebar {...baseProps} isMobile />)
    const handle = screen.getByRole("slider", { name: "sidebar.dragToResize" })
    const initialHeight = handle.getAttribute("aria-valuenow")

    fireEvent.keyDown(handle, { key: "Tab" })

    expect(handle).toHaveAttribute("aria-valuenow", initialHeight)
  })

  it("does not reschedule when a keyboard snap is already at its endpoint", () => {
    render(<MapSidebar {...baseProps} isMobile />)
    const handle = screen.getByRole("slider", { name: "sidebar.dragToResize" })

    fireEvent.keyDown(handle, { key: "End" })
    const fullHeight = handle.getAttribute("aria-valuenow")
    fireEvent.keyDown(handle, { key: "End" })

    expect(handle).toHaveAttribute("aria-valuenow", fullHeight)
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

  it("clamps a mobile drag and snaps to the nearest point on release", () => {
    render(<MapSidebar {...baseProps} isMobile />)
    const dialog = screen.getByRole("dialog")
    const handle = screen.getByRole("slider", { name: "sidebar.dragToResize" })
    const setPointerCapture = vi.fn()
    const releasePointerCapture = vi.fn()
    Object.defineProperty(handle, "setPointerCapture", { value: setPointerCapture })
    Object.defineProperty(handle, "releasePointerCapture", { value: releasePointerCapture })

    fireEvent.pointerDown(handle, { pointerId: 11, clientY: 500 })
    fireEvent.pointerMove(handle, { pointerId: 11, clientY: -100 })
    expect(Number(handle.getAttribute("aria-valuenow"))).toBe(Math.round(window.innerHeight * 0.9))
    fireEvent.pointerUp(handle, { pointerId: 11, clientY: -100 })
    expect(Number(handle.getAttribute("aria-valuenow"))).toBe(Math.round(window.innerHeight * 0.85))
    expect(dialog).toHaveStyle({ height: `${window.innerHeight * 0.85}px` })

    fireEvent.pointerDown(handle, { pointerId: 12, clientY: 500 })
    fireEvent.pointerMove(handle, { pointerId: 12, clientY: 2000 })
    expect(Number(handle.getAttribute("aria-valuenow"))).toBe(100)
    fireEvent.pointerUp(handle, { pointerId: 12, clientY: 2000 })
    expect(Number(handle.getAttribute("aria-valuenow"))).toBe(160)
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

  it("exposes the selected floor through radio semantics", () => {
    render(<MapSidebar {...baseProps} selectedFloor={2} />)
    expect(screen.getByRole("radio", { name: "1" })).toHaveAttribute("aria-checked", "false")
    expect(screen.getByRole("radio", { name: "2" })).toHaveAttribute("aria-checked", "true")
  })

  it("does not render a floor selector for a single-floor building", () => {
    render(
      <MapSidebar {...baseProps} building={{ ...BUILDING, floors: [FLOOR_1], floorCount: 1 }} />
    )
    expect(screen.queryByRole("radiogroup")).not.toBeInTheDocument()
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

  it("applies distinct status colors to free and busy room badges", () => {
    hooks.roomStatus = { status: "free" }
    const { rerender } = render(
      <MapSidebar {...baseProps} todayLessons={[{ room: "101", start_time: "10:00" }]} />
    )
    expect(screen.getByText("sidebar.roomFree")).toHaveStyle({
      color: "var(--color-emerald-500)",
    })

    hooks.roomStatus = { status: "busy", busyUntil: "11:30" }
    rerender(<MapSidebar {...baseProps} todayLessons={[{ room: "101", start_time: "10:00" }]} />)
    expect(screen.getByText(/sidebar\.roomBusy/)).toHaveStyle({ color: "var(--color-rose-500)" })
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

  it("remounts the scroll container when the selected building changes", () => {
    const { container, rerender } = render(<MapSidebar {...baseProps} />)
    const firstSidebar = container.querySelector(".map-sidebar-container")
    rerender(<MapSidebar {...baseProps} building={{ ...BUILDING, letter: "Б" }} />)
    expect(container.querySelector(".map-sidebar-container")).not.toBe(firstSidebar)
  })
})
