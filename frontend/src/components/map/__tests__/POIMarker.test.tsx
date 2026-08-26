import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi } from "vitest"
import type { ReactNode } from "react"

vi.mock("react-map-gl/maplibre", async () => {
  const { mapGlMock } = await import("@/tests/helpers/mapGlMock")
  return {
    ...mapGlMock(),
    Popup: ({
      children,
      closeButton,
      onClose,
    }: {
      children?: ReactNode
      closeButton?: boolean
      onClose?: () => void
    }) => (
      <div>
        {children}
        {closeButton ? (
          <button type="button" onClick={onClose}>
            popup-close
          </button>
        ) : null}
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

import { POIMarker } from "@/components/map/POIMarker"
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
  it("renders the POI pin with an accessible label", () => {
    render(<POIMarker {...baseProps} />)
    expect(screen.getByRole("button", { name: /poi\.items\.cafe-1\.name/ })).toHaveStyle({
      minWidth: "44px",
      minHeight: "44px",
    })
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

    fireEvent.pointerEnter(pin)
    expect(screen.getByText("poi.items.cafe-1.name")).toBeInTheDocument()
    fireEvent.pointerLeave(pin)
    expect(screen.queryByText("poi.items.cafe-1.name")).not.toBeInTheDocument()

    fireEvent.keyDown(pin, { key: "Enter" })
    fireEvent.keyDown(pin, { key: " " })
    fireEvent.keyDown(pin, { key: "Escape" })
    expect(onPopupOpen).toHaveBeenCalledTimes(2)
  })

  it("renders the full popup, closes it, and handles fallback naming/icon", async () => {
    const user = userEvent.setup()
    const onPopupClose = vi.fn()
    const openPopupView = render(
      <POIMarker {...baseProps} isPopupOpen onPopupClose={onPopupClose} />
    )
    expect(screen.getByText("poi.items.cafe-1.name")).toBeInTheDocument()
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
    expect(screen.getByRole("button", { name: /poi\.categories\.food/ })).toBeInTheDocument()
  })
})
