import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, it, expect, vi } from "vitest"
import type { ReactNode } from "react"
import {
  BookOpen,
  Bus,
  Coffee,
  Landmark,
  MapPin,
  ParkingCircle,
  Pill,
  ShoppingBag,
  ShoppingCart,
  TrainFront,
  UtensilsCrossed,
} from "lucide-react"

vi.mock("react-map-gl/maplibre", async () => {
  const { mapGlMock } = await import("@/tests/helpers/mapGlMock")
  const chromeReact = await import("react")
  return {
    ...mapGlMock(),
    Marker: chromeReact.forwardRef<
      { getElement: () => HTMLElement | null },
      { children?: import("react").ReactNode }
    >(function ChromeMarker({ children }, ref) {
      // Reproduces maplibre-gl's wrapper chrome (generic role/label/tabindex).
      const wrapper = chromeReact.useRef<HTMLDivElement>(null)
      chromeReact.useImperativeHandle(ref, () => ({ getElement: () => wrapper.current }))
      return chromeReact.createElement(
        "div",
        {
          ref: wrapper,
          role: "button",
          "aria-label": "Map marker",
          tabIndex: 0,
          "data-testid": "maplibre-marker-wrapper",
        },
        children
      )
    }),
    Popup: ({
      children,
      closeButton,
      closeOnClick,
      onClose,
      className,
      maxWidth,
    }: {
      children?: ReactNode
      closeButton?: boolean
      closeOnClick?: boolean
      onClose?: () => void
      className?: string
      maxWidth?: string
    }) => (
      <div
        className={className}
        data-close-on-click={String(closeOnClick)}
        data-max-width={maxWidth}
      >
        {children}
        {closeButton ? (
          <button type="button" onClick={onClose} aria-label="popup-close">
            popup-close
          </button>
        ) : null}
      </div>
    ),
  }
})
const translationMock = vi.hoisted(() =>
  vi.fn(() => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }))
)
vi.mock("react-i18next", () => ({ useTranslation: translationMock }))

import { getPoiIcon, POIMarker } from "@/components/map/POIMarker"
import type { CampusPOI } from "@/data/campusPOI"

const POI: CampusPOI = {
  id: "cafe-1",
  type: "food",
  coords: [55.71, 37.81],
  icon: "Coffee",
  i18nKey: "cafe-1",
}

const baseProps = { poi: POI }

describe("POIMarker", () => {
  beforeEach(() => {
    translationMock.mockClear()
  })

  it("renders the POI pin with an accessible label", () => {
    render(<POIMarker {...baseProps} />)
    const pin = screen.getByRole("button", {
      name: "poi.items.cafe-1.name — poi.categories.food",
    })
    expect(pin).toHaveStyle({
      minWidth: "44px",
      minHeight: "44px",
      "--_poi-color": "var(--map-poi-food, var(--color-slate-400, #94a3b8))",
    })
    expect(pin).toHaveAttribute("class", "map-poi-pin")
    expect(pin).not.toHaveClass("map-poi-pin--hover")
    expect(document.querySelector(".map-poi-tooltip")).toBeNull()
    expect(translationMock).toHaveBeenCalledWith("map")
    const iconMatrix = [
      ["BookOpen", BookOpen],
      ["TrainFront", TrainFront],
      ["Bus", Bus],
      ["UtensilsCrossed", UtensilsCrossed],
      ["Coffee", Coffee],
      ["ShoppingCart", ShoppingCart],
      ["ShoppingBag", ShoppingBag],
      ["Pill", Pill],
      ["Landmark", Landmark],
      ["ParkingCircle", ParkingCircle],
      ["MapPin", MapPin],
    ] as const
    for (const [name, icon] of iconMatrix) {
      expect(getPoiIcon(name)).toBe(icon)
    }
    expect(getPoiIcon("Unknown" as CampusPOI["icon"])).toBe(MapPin)
  })

  it("fires onPopupOpen when the pin is clicked", async () => {
    const user = userEvent.setup()
    const onPopupOpen = vi.fn()
    render(<POIMarker {...baseProps} onPopupOpen={onPopupOpen} />)
    await user.click(screen.getByRole("button", { name: /poi\.items\.cafe-1\.name/ }))
    expect(onPopupOpen).toHaveBeenCalledOnce()
  })

  it("shows and hides the hover tooltip and supports keyboard activation", () => {
    const onPopupOpen = vi.fn()
    render(<POIMarker {...baseProps} onPopupOpen={onPopupOpen} />)
    const pin = screen.getByRole("button", { name: /poi\.items\.cafe-1\.name/ })

    expect(screen.queryByText("poi.items.cafe-1.name")).not.toBeInTheDocument()
    expect(document.querySelector(".map-poi-tooltip")).toBeNull()
    fireEvent.pointerEnter(pin)
    expect(pin).toHaveClass("map-poi-pin--hover")
    expect(screen.getByText("poi.items.cafe-1.name")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "popup-close" })).not.toBeInTheDocument()
    expect(document.querySelector(".map-poi-tooltip")).toHaveAttribute(
      "data-close-on-click",
      "false"
    )
    fireEvent.pointerLeave(pin)
    expect(pin).not.toHaveClass("map-poi-pin--hover")
    expect(screen.queryByText("poi.items.cafe-1.name")).not.toBeInTheDocument()
    expect(document.querySelector(".map-poi-tooltip")).toBeNull()

    fireEvent.keyDown(pin, { key: "Enter" })
    fireEvent.keyDown(pin, { key: " " })
    fireEvent.keyDown(pin, { key: "Escape" })
    fireEvent.keyDown(pin, { key: "a" })
    expect(onPopupOpen).toHaveBeenCalledTimes(2)
  })

  it("is safe when popup callbacks are omitted", () => {
    const view = render(<POIMarker {...baseProps} />)
    const pin = screen.getByRole("button", { name: /poi\.items\.cafe-1\.name/ })

    expect(() => fireEvent.click(pin)).not.toThrow()
    expect(() => fireEvent.keyDown(pin, { key: "Enter" })).not.toThrow()
    view.unmount()

    expect(() => render(<POIMarker {...baseProps} isPopupOpen />)).not.toThrow()
  })

  it("renders the full popup, closes it, and handles fallback naming/icon", async () => {
    const user = userEvent.setup()
    const onPopupClose = vi.fn()
    const openPopupView = render(
      <POIMarker {...baseProps} isPopupOpen onPopupClose={onPopupClose} />
    )
    expect(screen.getByText("poi.items.cafe-1.name")).toBeInTheDocument()
    expect(screen.getByText("poi.categories.food")).toBeInTheDocument()
    expect(document.querySelector(".map-popup-premium")).toHaveAttribute(
      "data-close-on-click",
      "false"
    )
    expect(document.querySelector(".map-popup-premium")).toHaveAttribute("data-max-width", "240px")
    expect(document.querySelector(".map-popup-card--compact .rounded-full")).toHaveStyle({
      backgroundColor: "var(--map-poi-food, var(--color-slate-400, #94a3b8))",
    })
    expect(screen.getByRole("link", { name: /poi\.openInMaps/ })).toHaveAttribute(
      "href",
      expect.stringContaining("yandex.ru/maps")
    )
    await user.click(screen.getByRole("button", { name: "popup-close" }))
    expect(onPopupClose).toHaveBeenCalledOnce()
    openPopupView.unmount()

    const fallbackPoi = {
      ...POI,
      i18nKey: undefined,
      osmName: "Campus cafe",
      icon: "Unknown" as CampusPOI["icon"],
    }
    const namedFallbackView = render(<POIMarker poi={fallbackPoi} />)
    expect(screen.getByRole("button", { name: /Campus cafe/ })).toBeInTheDocument()
    namedFallbackView.unmount()

    render(<POIMarker poi={{ ...fallbackPoi, osmName: undefined }} />)
    const categoryPin = screen.getByRole("button", { name: /poi\.categories\.food/ })
    expect(categoryPin).toHaveAttribute("aria-label", "poi.categories.food — poi.categories.food")
  })
})

describe("POIMarker maplibre integration", () => {
  it("strips maplibre's generic button chrome so the pin is the only control", () => {
    render(<POIMarker {...baseProps} />)
    const wrapper = screen.getByTestId("maplibre-marker-wrapper")

    expect(wrapper).not.toHaveAttribute("role")
    expect(wrapper).not.toHaveAttribute("aria-label")
    expect(wrapper).not.toHaveAttribute("tabindex")
    expect(screen.getAllByRole("button")).toHaveLength(1)
  })

  it("keeps pin clicks from reaching the map canvas", () => {
    const mapClick = vi.fn()
    render(
      <div role="presentation" onClick={mapClick}>
        <POIMarker {...baseProps} />
      </div>
    )

    fireEvent.click(screen.getByTestId("maplibre-marker-wrapper").firstElementChild!)

    expect(mapClick).not.toHaveBeenCalled()
  })

  it("cancels native Enter and Space handling on the pin", () => {
    render(<POIMarker {...baseProps} />)
    const pin = screen.getByTestId("maplibre-marker-wrapper").firstElementChild!

    expect(fireEvent.keyDown(pin, { key: "Enter" })).toBe(false)
    expect(fireEvent.keyDown(pin, { key: " " })).toBe(false)
    expect(fireEvent.keyDown(pin, { key: "Tab" })).toBe(true)
  })
})
