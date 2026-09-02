import { act, createEvent, fireEvent, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { CampusBuilding, BuildingFloor } from "@/data/campusBuildings"

const state = vi.hoisted(() => ({
  open: true,
  roomStatus: null as { status: "free" | "busy"; busyUntil?: string } | null,
  setOverlayState: vi.fn(),
  useFocusTrap: vi.fn(() => ({ current: null })),
}))

const mockUseTranslation = vi.hoisted(() => vi.fn())

function translate(key: string, options?: Record<string, unknown>) {
  return options && Object.keys(options).length > 0 ? `${key}:${JSON.stringify(options)}` : key
}

vi.mock("react-i18next", () => ({ useTranslation: mockUseTranslation }))
vi.mock("@/contexts/AppShellContext", () => ({
  useAppShell: () => ({ setOverlayState: state.setOverlayState }),
}))
vi.mock("@/hooks/useFocusTrap", () => ({ default: state.useFocusTrap }))
vi.mock("@/utils/buildingHours", () => ({ isOpenNow: () => state.open }))
vi.mock("@/utils/roomStatus", () => ({
  getRoomStatus: vi.fn(() => state.roomStatus),
}))

import {
  getDragMoveDeps,
  getInitialSheetReadyState,
  getMobileSheetSafeAreaPadding,
  getOverlayEffectDeps,
  getScrollKey,
  getSheetResetHeight,
  getSnapPointMemoDeps,
  getSnapToNearestDeps,
  applySheetResetHeight,
  shouldApplySheetResetHeight,
  MapSidebar,
} from "@/components/map/MapSidebar"

const NAMED_ROOM = {
  id: "ГУК-101",
  number: "101",
  type: "lecture" as const,
  capacity: 120,
  name: "Большая аудитория",
}
const PLAIN_ROOM = {
  id: "ГУК-102",
  number: "102",
  type: "seminar" as const,
}
const FLOOR_1: BuildingFloor = { floor: 1, rooms: [NAMED_ROOM, PLAIN_ROOM] }
const FLOOR_2: BuildingFloor = {
  floor: 2,
  rooms: [{ id: "ГУК-201", number: "201", type: "lab", capacity: 24 }],
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
const OTHER_BUILDING: CampusBuilding = {
  ...BUILDING,
  letter: "ПА",
  structureId: "стр. 6",
  name: "Приёмная администрация",
  description: "Административный корпус.",
  address: "Рязанский проспект, 97",
  colorVar: "var(--color-amber-500)",
  colorHex: "#f59e0b",
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

function latestFocusTrapOptions() {
  const calls = state.useFocusTrap.mock.calls as unknown[][]
  return calls[calls.length - 1]?.[0] as Record<string, unknown> | undefined
}

function getRoomButton(roomId: string) {
  const roomButton = screen
    .getAllByRole("button")
    .find((button) => button.textContent?.includes(roomId))
  expect(roomButton).toBeDefined()
  return roomButton as HTMLElement
}

beforeEach(() => {
  state.open = true
  state.roomStatus = null
  state.setOverlayState.mockReset()
  state.useFocusTrap.mockReset().mockImplementation(() => ({ current: null }))
  mockUseTranslation.mockReset().mockImplementation(() => ({
    t: translate,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }))
  Object.defineProperty(window, "innerHeight", { configurable: true, value: 800 })
  vi.useRealTimers()
})

describe("MapSidebar mutation contracts", () => {
  it("keeps the SSR, dependency, and sheet transition contracts explicit", () => {
    const setOverlayState = vi.fn()

    expect(getMobileSheetSafeAreaPadding()).toBe("env(safe-area-inset-bottom, 0px)")
    expect(getSnapPointMemoDeps()).toEqual([])
    expect(getOverlayEffectDeps(true, true, setOverlayState)).toEqual([true, true, setOverlayState])
    expect(getSnapToNearestDeps(160, 400, 680)).toEqual([160, 400, 680])
    expect(getDragMoveDeps()).toEqual([])
    expect(getInitialSheetReadyState()).toBe(false)
    expect(getSheetResetHeight(true, 400)).toBe(400)
    expect(getSheetResetHeight(false, 400)).toBeUndefined()
    expect(shouldApplySheetResetHeight(400)).toBe(true)
    expect(shouldApplySheetResetHeight(undefined)).toBe(false)
    const setSheetHeight = vi.fn()
    applySheetResetHeight(400, setSheetHeight)
    applySheetResetHeight(undefined, setSheetHeight)
    expect(setSheetHeight).toHaveBeenCalledTimes(1)
    expect(setSheetHeight).toHaveBeenCalledWith(400)
    expect(getScrollKey(BUILDING)).toBe("ГУК")
    expect(getScrollKey(undefined)).toBe("")
  })

  it("does not schedule an entrance timer without a building", () => {
    vi.useFakeTimers()
    const view = render(
      <MapSidebar {...baseProps} isMobile building={undefined} floor={undefined} />
    )
    expect(vi.getTimerCount()).toBe(0)

    view.rerender(<MapSidebar {...baseProps} isMobile />)
    expect(vi.getTimerCount()).toBe(1)
    act(() => vi.advanceTimersByTime(260))
    expect(screen.getByRole("dialog").querySelector(".overflow-y-auto")).toBeInTheDocument()
  })

  it("uses the map translation namespace and exposes the desktop shell contract", () => {
    render(<MapSidebar {...baseProps} />)

    expect(mockUseTranslation).toHaveBeenCalledWith("map")
    const sidebar = document.querySelector(".map-sidebar-container") as HTMLElement
    expect(sidebar).toBeInTheDocument()
    expect(sidebar.style.backgroundColor).toBe("var(--map-sidebar-bg)")
    expect(sidebar.style.boxShadow).toBe("var(--map-sidebar-shadow)")
    expect(sidebar.style.maxHeight).toBe("calc(100vh - 200px)")
  })

  it("keeps mobile overlay state untouched unless an open mobile sheet exists", () => {
    const desktop = render(<MapSidebar {...baseProps} isMobile={false} />)
    expect(state.setOverlayState).not.toHaveBeenCalled()
    desktop.unmount()

    const closed = render(
      <MapSidebar {...baseProps} isMobile building={undefined} floor={undefined} />
    )
    expect(state.setOverlayState).not.toHaveBeenCalled()
    closed.unmount()

    const open = render(<MapSidebar {...baseProps} isMobile />)
    expect(state.setOverlayState).toHaveBeenCalledWith("map-sidebar", {
      scrollLocked: true,
      blurred: false,
    })

    open.rerender(<MapSidebar {...baseProps} isMobile building={undefined} floor={undefined} />)
    expect(state.setOverlayState).toHaveBeenLastCalledWith("map-sidebar", null)
  })

  it("passes the mobile focus-trap activation, close callback, and initial-focus policy", () => {
    const onClose = vi.fn()
    const { rerender } = render(<MapSidebar {...baseProps} isMobile onClose={onClose} />)

    let options = latestFocusTrapOptions()
    expect(options).toMatchObject({ active: true, initialFocus: false })
    expect(options?.onDeactivate).toBe(onClose)

    rerender(<MapSidebar {...baseProps} isMobile={false} onClose={onClose} />)
    options = latestFocusTrapOptions()
    expect(options?.active).toBe(false)

    rerender(
      <MapSidebar
        {...baseProps}
        isMobile
        onClose={onClose}
        building={undefined}
        floor={undefined}
      />
    )
    options = latestFocusTrapOptions()
    expect(options?.active).toBe(false)
  })

  it("renders deterministic initial mobile geometry and safe-area styles", () => {
    vi.useFakeTimers()
    const { container } = render(<MapSidebar {...baseProps} isMobile />)
    const dialog = screen.getByRole("dialog")
    const handle = screen.getByRole("slider", { name: "sidebar.dragToResize" })
    const scrollArea = container.querySelector(".scrollbar-hide") as HTMLElement

    expect(dialog.style.height).toBe("400px")
    expect(getMobileSheetSafeAreaPadding()).toBe("env(safe-area-inset-bottom, 0px)")
    expect(dialog.style.boxShadow).toBe("var(--map-sidebar-shadow)")
    expect(handle).toHaveAttribute("aria-valuemin", "100")
    expect(handle).toHaveAttribute("aria-valuemax", "720")
    expect(handle).toHaveAttribute("aria-valuenow", "400")
    expect(scrollArea).toHaveClass("overflow-hidden", "scrollbar-hide")
    expect(scrollArea.style.height).toBe("360px")
    act(() => vi.advanceTimersByTime(260))
    expect(scrollArea).toHaveClass("overflow-y-auto")
  })

  it("requires pointer-down before drag movement or release and ends the drag after release", () => {
    const { unmount } = render(<MapSidebar {...baseProps} isMobile />)
    const handle = screen.getByRole("slider", { name: "sidebar.dragToResize" })
    const setPointerCapture = vi.fn()
    const releasePointerCapture = vi.fn()
    Object.defineProperty(handle, "setPointerCapture", {
      configurable: true,
      value: setPointerCapture,
    })
    Object.defineProperty(handle, "releasePointerCapture", {
      configurable: true,
      value: releasePointerCapture,
    })

    fireEvent.pointerMove(handle, { pointerId: 7, clientY: 600 })
    fireEvent.pointerUp(handle, { pointerId: 7, clientY: 600 })
    expect(handle).toHaveAttribute("aria-valuenow", "400")
    expect(releasePointerCapture).not.toHaveBeenCalled()

    fireEvent.pointerDown(handle, { pointerId: 7, clientY: 500 })
    fireEvent.pointerMove(handle, { pointerId: 7, clientY: 600 })
    expect(handle).toHaveAttribute("aria-valuenow", "300")
    fireEvent.pointerUp(handle, { pointerId: 7, clientY: 600 })
    expect(setPointerCapture).toHaveBeenCalledWith(7)
    expect(releasePointerCapture).toHaveBeenCalledWith(7)
    expect(handle).toHaveAttribute("aria-valuenow", "400")

    fireEvent.pointerMove(handle, { pointerId: 7, clientY: 300 })
    expect(handle).toHaveAttribute("aria-valuenow", "400")
    unmount()
  })

  it("refreshes the drag handler when the responsive mode changes", () => {
    const view = render(<MapSidebar {...baseProps} isMobile={false} />)
    view.rerender(<MapSidebar {...baseProps} isMobile />)
    const handle = screen.getByRole("slider", { name: "sidebar.dragToResize" })
    const setPointerCapture = vi.fn()
    const releasePointerCapture = vi.fn()
    Object.defineProperty(handle, "setPointerCapture", {
      configurable: true,
      value: setPointerCapture,
    })
    Object.defineProperty(handle, "releasePointerCapture", {
      configurable: true,
      value: releasePointerCapture,
    })

    fireEvent.pointerDown(handle, { pointerId: 9, clientY: 500 })
    fireEvent.pointerMove(handle, { pointerId: 9, clientY: 600 })
    expect(handle).toHaveAttribute("aria-valuenow", "300")
    fireEvent.pointerUp(handle, { pointerId: 9, clientY: 600 })
    expect(handle).toHaveAttribute("aria-valuenow", "400")
  })

  it("snaps a drag to the lower point on a midpoint and keeps the nearest point arithmetic", () => {
    const { container } = render(<MapSidebar {...baseProps} isMobile />)
    const handle = screen.getByRole("slider", { name: "sidebar.dragToResize" })
    const setPointerCapture = vi.fn()
    const releasePointerCapture = vi.fn()
    Object.defineProperty(handle, "setPointerCapture", {
      configurable: true,
      value: setPointerCapture,
    })
    Object.defineProperty(handle, "releasePointerCapture", {
      configurable: true,
      value: releasePointerCapture,
    })

    // 280 is exactly halfway between the 160px and 400px snap points.
    fireEvent.pointerDown(handle, { pointerId: 1, clientY: 500 })
    fireEvent.pointerMove(handle, { pointerId: 1, clientY: 620 })
    fireEvent.pointerUp(handle, { pointerId: 1, clientY: 620 })
    expect(handle).toHaveAttribute("aria-valuenow", "160")

    // At the peek point, the nearest point must remain the peek point.
    fireEvent.pointerDown(handle, { pointerId: 2, clientY: 500 })
    fireEvent.pointerMove(handle, { pointerId: 2, clientY: 500 })
    fireEvent.pointerUp(handle, { pointerId: 2, clientY: 500 })
    expect(handle).toHaveAttribute("aria-valuenow", "160")
    expect(container.querySelector('[aria-valuenow="160"]')).toBe(handle)
  })

  it("supports every bounded keyboard resize direction and ignores unknown keys", () => {
    const handle = render(<MapSidebar {...baseProps} isMobile />).getByRole("slider", {
      name: "sidebar.dragToResize",
    })

    fireEvent.keyDown(handle, { key: "ArrowDown" })
    expect(handle).toHaveAttribute("aria-valuenow", "160")
    fireEvent.keyDown(handle, { key: "ArrowUp" })
    expect(handle).toHaveAttribute("aria-valuenow", "400")
    fireEvent.keyDown(handle, { key: "ArrowRight" })
    expect(handle).toHaveAttribute("aria-valuenow", "680")
    fireEvent.keyDown(handle, { key: "ArrowLeft" })
    expect(handle).toHaveAttribute("aria-valuenow", "400")
    // A second increase at the upper endpoint must remain bounded.
    fireEvent.keyDown(handle, { key: "ArrowRight" })
    expect(handle).toHaveAttribute("aria-valuenow", "680")
    fireEvent.keyDown(handle, { key: "ArrowRight" })
    expect(handle).toHaveAttribute("aria-valuenow", "680")
    fireEvent.keyDown(handle, { key: "ArrowLeft" })
    expect(handle).toHaveAttribute("aria-valuenow", "400")
    fireEvent.keyDown(handle, { key: "ArrowLeft" })
    expect(handle).toHaveAttribute("aria-valuenow", "160")
    fireEvent.keyDown(handle, { key: "PageUp" })
    expect(handle).toHaveAttribute("aria-valuenow", "400")
    fireEvent.keyDown(handle, { key: "PageDown" })
    expect(handle).toHaveAttribute("aria-valuenow", "160")
    fireEvent.keyDown(handle, { key: "ArrowDown" })
    expect(handle).toHaveAttribute("aria-valuenow", "160")
    fireEvent.keyDown(handle, { key: "ArrowUp" })
    expect(handle).toHaveAttribute("aria-valuenow", "400")
    fireEvent.keyDown(handle, { key: "Home" })
    expect(handle).toHaveAttribute("aria-valuenow", "160")
    fireEvent.keyDown(handle, { key: "End" })
    expect(handle).toHaveAttribute("aria-valuenow", "680")

    fireEvent.keyDown(handle, { key: "Escape" })
    expect(handle).toHaveAttribute("aria-valuenow", "680")
  })

  it("uses the lower keyboard snap point on an exact midpoint", () => {
    const handle = render(<MapSidebar {...baseProps} isMobile />).getByRole("slider", {
      name: "sidebar.dragToResize",
    })
    const setPointerCapture = vi.fn()
    const releasePointerCapture = vi.fn()
    Object.defineProperty(handle, "setPointerCapture", {
      configurable: true,
      value: setPointerCapture,
    })
    Object.defineProperty(handle, "releasePointerCapture", {
      configurable: true,
      value: releasePointerCapture,
    })

    fireEvent.pointerDown(handle, { pointerId: 1, clientY: 500 })
    fireEvent.pointerMove(handle, { pointerId: 1, clientY: 620 })
    expect(handle).toHaveAttribute("aria-valuenow", "280")
    fireEvent.keyDown(handle, { key: "ArrowUp" })
    expect(handle).toHaveAttribute("aria-valuenow", "400")
    fireEvent.pointerUp(handle, { pointerId: 1, clientY: 620 })
  })

  it("does not cancel endpoint keyboard events that cannot change the sheet", () => {
    const handle = render(<MapSidebar {...baseProps} isMobile />).getByRole("slider", {
      name: "sidebar.dragToResize",
    })
    fireEvent.keyDown(handle, { key: "End" })
    const event = createEvent.keyDown(handle, { key: "End" })
    fireEvent(handle, event)
    expect(event.defaultPrevented).toBe(false)
  })

  it("resets mobile height and sheet readiness for each building and cleans up timers", () => {
    vi.useFakeTimers()
    const clearTimeoutSpy = vi.spyOn(window, "clearTimeout")
    const { rerender } = render(<MapSidebar {...baseProps} isMobile />)
    const handle = screen.getByRole("slider", { name: "sidebar.dragToResize" })
    const setPointerCapture = vi.fn()
    const releasePointerCapture = vi.fn()
    Object.defineProperty(handle, "setPointerCapture", {
      configurable: true,
      value: setPointerCapture,
    })
    Object.defineProperty(handle, "releasePointerCapture", {
      configurable: true,
      value: releasePointerCapture,
    })
    act(() => vi.advanceTimersByTime(260))

    fireEvent.pointerDown(handle, { pointerId: 1, clientY: 500 })
    fireEvent.pointerMove(handle, { pointerId: 1, clientY: 740 })
    fireEvent.pointerUp(handle, { pointerId: 1, clientY: 740 })
    expect(handle).toHaveAttribute("aria-valuenow", "160")

    rerender(<MapSidebar {...baseProps} isMobile building={OTHER_BUILDING} />)
    expect(clearTimeoutSpy).toHaveBeenCalled()
    const dialog = screen.getByRole("dialog")
    const scrollArea = dialog.querySelector(".scrollbar-hide") as HTMLElement
    expect(dialog).toHaveAttribute("aria-labelledby")
    expect(dialog.style.height).toBe("400px")
    expect(scrollArea).toHaveClass("overflow-hidden")
    act(() => vi.advanceTimersByTime(260))
    expect(scrollArea).toHaveClass("overflow-y-auto")
  })

  it("renders active and inactive room semantics, names, and stable room actions", async () => {
    const user = userEvent.setup()
    const onRoomClick = vi.fn()
    const { rerender } = render(
      <MapSidebar {...baseProps} selectedRoom="ГУК-101" onRoomClick={onRoomClick} />
    )
    const activeRoom = getRoomButton("ГУК-101")
    const plainRoom = getRoomButton("ГУК-102")

    expect(activeRoom).toHaveClass("map-accent-tint-light", "flex", "items-center")
    expect(activeRoom.querySelector(".truncate")).toHaveTextContent("Большая аудитория")
    expect(activeRoom.querySelector(".font-bold")).toHaveStyle({ color: "var(--_bldg-color)" })
    expect(plainRoom).not.toHaveClass("map-accent-tint-light")
    expect(plainRoom.querySelector(".truncate")).not.toBeInTheDocument()
    expect(plainRoom.querySelector(".font-bold")).not.toHaveStyle({ color: "var(--_bldg-color)" })

    await user.click(plainRoom)
    expect(onRoomClick).toHaveBeenCalledWith("ГУК-102")

    rerender(<MapSidebar {...baseProps} selectedRoom={null} onRoomClick={onRoomClick} />)
    expect(getRoomButton("ГУК-101")).not.toHaveClass("map-accent-tint-light")
  })

  it("keeps the room list absent when a selected building has no floor", () => {
    render(<MapSidebar {...baseProps} floor={undefined} />)

    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent(BUILDING.name)
    expect(screen.queryByText(/sidebar\.rooms/)).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /ГУК-101/ })).not.toBeInTheDocument()
  })

  it("renders free and busy status badges with exact copy and color contracts", () => {
    state.roomStatus = { status: "free" }
    const { rerender } = render(
      <MapSidebar {...baseProps} todayLessons={[{ room: "ГУК-101", start_time: "10:00" }]} />
    )
    const free = screen.getAllByText("sidebar.roomFree")[0]!
    expect(free).toHaveStyle({
      backgroundColor: "color-mix(in srgb, var(--color-emerald-500) 15%, transparent)",
      color: "var(--color-emerald-500)",
    })

    state.roomStatus = { status: "busy", busyUntil: "11:30" }
    rerender(
      <MapSidebar {...baseProps} todayLessons={[{ room: "ГУК-101", start_time: "10:00" }]} />
    )
    const busy = screen.getAllByText('sidebar.roomBusy:{"time":"11:30"}')[0]!
    expect(busy).toHaveStyle({
      backgroundColor: "color-mix(in srgb, var(--color-rose-500) 15%, transparent)",
      color: "var(--color-rose-500)",
    })
  })

  it("renders selected-room details only for available optional name and capacity", () => {
    const { rerender } = render(<MapSidebar {...baseProps} selectedRoom="ГУК-101" />)
    const detail = document.querySelector(".map-card-matte.p-3") as HTMLElement
    expect(detail).toBeInTheDocument()
    expect(within(detail).getByText("ГУК-101")).toHaveStyle({ color: "#3b82f6" })
    expect(within(detail).getByText("Большая аудитория")).toBeInTheDocument()
    expect(within(detail).getByTestId("selected-room-name")).toHaveTextContent("Большая аудитория")
    expect(within(detail).getByText("roomTypes.lecture")).toBeInTheDocument()
    expect(within(detail).getByText("120")).toBeInTheDocument()
    expect(detail.querySelector("p.flex")).toHaveTextContent("120")

    rerender(<MapSidebar {...baseProps} selectedRoom="ГУК-102" />)
    const noOptionalDetail = document.querySelector(".map-card-matte.p-3") as HTMLElement
    expect(noOptionalDetail).toBeInTheDocument()
    expect(within(noOptionalDetail).queryByText("Большая аудитория")).not.toBeInTheDocument()
    expect(within(noOptionalDetail).queryByTestId("selected-room-name")).not.toBeInTheDocument()
    expect(noOptionalDetail.querySelector("p.flex")).not.toBeInTheDocument()
  })

  it("keeps the room-list heading interpolation and action geometry explicit", () => {
    render(<MapSidebar {...baseProps} />)

    expect(screen.getByText('sidebar.rooms — sidebar.roomCount:{"count":2}')).toBeInTheDocument()
    const roomButton = getRoomButton("ГУК-101")
    expect(roomButton).toHaveClass(
      "flex",
      "items-center",
      "justify-between",
      "gap-2",
      "px-3",
      "py-2",
      "rounded-lg",
      "text-left",
      "transition-colors",
      "text-xs"
    )
  })

  it("renders placeholder/header colors and both open and closed hour styles", () => {
    const { rerender } = render(<MapSidebar {...baseProps} />)
    const placeholder = document.querySelector(".map-sidebar-photo-placeholder") as HTMLElement
    expect(placeholder.style.background).toContain("rgb(59, 130, 246)")
    expect(placeholder.style.background).toContain("color-mix")
    const letter = document.querySelector(".font-black.text-lg") as HTMLElement
    expect(letter.style.backgroundColor).toBe("rgb(59, 130, 246)")
    expect(letter.style.color).toBe("var(--map-on-accent)")

    const hourLabels = Array.from(document.querySelectorAll(".font-semibold")).map((node) =>
      node.textContent?.trim()
    )
    expect(hourLabels).toEqual(
      expect.arrayContaining(["hours.weekday:", "hours.saturday:", "hours.sunday:"])
    )
    expect(screen.getByText("08:00–22:00")).toBeInTheDocument()
    expect(screen.getByText("09:00–20:00")).toBeInTheDocument()
    expect(screen.getByText("Закрыто")).toBeInTheDocument()
    expect(screen.getByText("sidebar.floor")).toBeInTheDocument()
    expect(screen.getByRole("radiogroup", { name: "floorPlan.selectFloor" })).toBeInTheDocument()

    const open = screen.getByText("hours.openNow")
    expect(open).toHaveStyle({
      backgroundColor: "color-mix(in srgb, var(--color-emerald-500) 15%, transparent)",
      color: "var(--color-emerald-500)",
    })

    state.open = false
    rerender(<MapSidebar {...baseProps} />)
    const closed = screen.getByText("hours.closedNow")
    expect(closed).toHaveStyle({
      backgroundColor: "color-mix(in srgb, var(--color-rose-500) 15%, transparent)",
      color: "var(--color-rose-500)",
    })
  })

  it("exposes floor radio selection, target sizes, and active/inactive colors", () => {
    render(<MapSidebar {...baseProps} selectedFloor={2} />)
    const floorOne = screen.getByRole("radio", { name: "1" })
    const floorTwo = screen.getByRole("radio", { name: "2" })

    expect(floorOne).toHaveAttribute("aria-checked", "false")
    expect(floorOne).not.toHaveClass("map-accent-tint-medium")
    expect(floorOne.className).toBe(
      "min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg text-xs font-bold transition-colors"
    )
    expect(floorOne).toHaveStyle({
      backgroundColor: "var(--bg-surface-hover)",
      color: "var(--text-secondary)",
    })
    expect(floorOne).toHaveClass("min-h-[44px]", "min-w-[44px]")
    expect(floorTwo).toHaveAttribute("aria-checked", "true")
    expect(floorTwo).toHaveClass("map-accent-tint-medium")
    expect(floorTwo.className).toBe(
      "min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg text-xs font-bold transition-colors map-accent-tint-medium"
    )
    expect(floorTwo).toHaveStyle({ color: "var(--_bldg-color)" })
  })

  it("keeps the mobile sheet scroll area dimensions and classes stable", () => {
    const { container } = render(<MapSidebar {...baseProps} isMobile />)
    const dialog = screen.getByRole("dialog")
    const scrollArea = container.querySelector(".scrollbar-hide") as HTMLElement

    expect(dialog).toHaveAttribute("aria-modal", "true")
    expect(dialog).toHaveAttribute("aria-labelledby")
    expect(dialog).toHaveAttribute("aria-describedby")
    expect(scrollArea.className).toContain("overflow-hidden")
    expect(scrollArea.className).toContain("scrollbar-hide")
    expect(scrollArea.style.height).toBe("360px")
  })
})
