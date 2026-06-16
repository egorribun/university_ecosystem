import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi } from "vitest"

vi.mock("react-map-gl/maplibre", async () =>
  (await import("@/tests/helpers/mapGlMock")).mapGlMock()
)
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
    expect(screen.getByRole("button", { name: /poi\.items\.cafe-1\.name/ })).toBeInTheDocument()
  })

  it("fires onPopupOpen when the pin is clicked", async () => {
    const user = userEvent.setup()
    const onPopupOpen = vi.fn()
    render(<POIMarker {...baseProps} onPopupOpen={onPopupOpen} />)
    await user.click(screen.getByRole("button", { name: /poi\.items\.cafe-1\.name/ }))
    expect(onPopupOpen).toHaveBeenCalledOnce()
  })

  it("renders the full popup with an external maps link when open", () => {
    render(<POIMarker {...baseProps} isPopupOpen />)
    expect(screen.getByText("poi.items.cafe-1.name")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /poi\.openInMaps/ })).toHaveAttribute(
      "href",
      expect.stringContaining("yandex.ru/maps")
    )
  })
})
