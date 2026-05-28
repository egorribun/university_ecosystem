import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { Map } from "react-map-gl/maplibre"
import type { StyleSpecification } from "maplibre-gl"
import "maplibre-gl/dist/maplibre-gl.css"
import { POIMarker } from "./POIMarker"
import { CAMPUS_POIS } from "@/data/campusPOI"

// Wave 194 SW4 — POIMarker Storybook fixture (MapLibre-in-Storybook proven by the
// BuildingMarker spike). Same minimal <Map> + empty offline style decorator.
// POIMarker is a <Marker anchor="center"> with a category Lucide icon + hover
// tooltip + click popup (a plain <a> to Yandex Maps — no TanStack Link). Uses
// real POI data from CAMPUS_POIS. Coord gotcha FIX-100-01: poi.coords [lat,lng]
// → longitude={[1]} latitude={[0]} (never swap).
//
// Variants: Default (transport), Food (food-category icon/color), PopupOpen, DarkMode.

const transportPoi = CAMPUS_POIS.find((p) => p.type === "transport") ?? CAMPUS_POIS[0]!
const foodPoi = CAMPUS_POIS.find((p) => p.type === "food") ?? transportPoi

const EMPTY_STYLE: StyleSpecification = { version: 8, sources: {}, layers: [] }

const mapDecorator = (lng: number, lat: number, dark = false): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div
        className="map-theme relative"
        style={{
          width: 420,
          height: 420,
          overflow: "hidden",
          borderRadius: 12,
          background: "var(--bg-page)",
        }}
      >
        <Map
          initialViewState={{ longitude: lng, latitude: lat, zoom: 17, pitch: 0, bearing: 0 }}
          mapStyle={EMPTY_STYLE}
          style={{ width: "100%", height: "100%" }}
          attributionControl={false}
        >
          <Story />
        </Map>
      </div>
    </div>
  )
}

const meta: Meta<typeof POIMarker> = {
  title: "Map/POIMarker",
  component: POIMarker,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof POIMarker>

export const Default: Story = {
  args: { poi: transportPoi },
  decorators: [mapDecorator(transportPoi.coords[1], transportPoi.coords[0])],
}

export const Food: Story = {
  args: { poi: foodPoi },
  decorators: [mapDecorator(foodPoi.coords[1], foodPoi.coords[0])],
  parameters: {
    docs: {
      description: {
        story: "Food-category POI — different Lucide icon + --map-poi-food color token.",
      },
    },
  },
}

export const PopupOpen: Story = {
  args: { poi: transportPoi, isPopupOpen: true },
  decorators: [mapDecorator(transportPoi.coords[1], transportPoi.coords[0])],
  parameters: {
    docs: {
      description: {
        story: "Click popup — compact card with category label + 'Open in Maps' link.",
      },
    },
  },
}

export const DarkMode: Story = {
  args: { poi: transportPoi },
  decorators: [mapDecorator(transportPoi.coords[1], transportPoi.coords[0], true)],
  parameters: { backgrounds: { default: "dark" } },
}
