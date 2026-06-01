import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { Map } from "react-map-gl/maplibre"
import type { StyleSpecification } from "maplibre-gl"
import "maplibre-gl/dist/maplibre-gl.css"
import { BuildingMarker } from "./BuildingMarker"
import { getCampusBuildings } from "@/data/campusBuildings"

// Wave 194 SW4 — BuildingMarker Storybook fixture (SPIKE for the Map-marker group).
//
// Each marker is a react-map-gl/maplibre <Marker> child that REQUIRES a live
// MapLibre GL <Map> context — so the decorator wraps the story in a minimal
// <Map> centered on the building, using an EMPTY offline mapStyle
// ({version:8, sources:{}, layers:[]}) so Storybook needs NO network tile fetch
// (markers are HTML overlays positioned over the blank basemap). The Storybook
// iframe is a real Chromium with WebGL, so maplibre-gl should init (unlike the
// Wave 147 SW5 HEADLESS-chromium canvas-never-visible case). The marker overlay
// is positioned by maplibre's projection once <Map> initializes, independent of
// whether basemap tiles paint. useStripMaplibreMarkerChrome no-ops safely while
// the ref is null. Coord gotcha FIX-100-01: data is geoCoords [lat,lng] but
// MapLibre needs longitude={[1]} latitude={[0]} — never swap indices.
//
// Variants: Default, Selected, Highlighted, PopupOpen, DarkMode.

const building = getCampusBuildings("en")[0]!

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

const meta: Meta<typeof BuildingMarker> = {
  title: "Map/BuildingMarker",
  component: BuildingMarker,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof BuildingMarker>

const baseArgs = {
  building,
  isSelected: false,
  isHighlighted: false,
  onClick: () => {},
}

const decorators = [mapDecorator(building.geoCoords[1], building.geoCoords[0])]

export const Default: Story = {
  args: baseArgs,
  decorators,
}

export const Selected: Story = {
  args: { ...baseArgs, isSelected: true },
  decorators,
  parameters: {
    docs: {
      description: { story: "Clicked/active state — larger pin per BuildingMarker.tsx:96." },
    },
  },
}

export const Highlighted: Story = {
  args: { ...baseArgs, isHighlighted: true },
  decorators,
  parameters: {
    docs: {
      description: { story: "Schedule next-lesson highlight — subtle pulse, not full active." },
    },
  },
}

export const PopupOpen: Story = {
  args: { ...baseArgs, isSelected: true, isPopupOpen: true },
  decorators,
  parameters: {
    docs: {
      description: {
        story: "Premium popup card: photo placeholder + stats + open-now + amenities.",
      },
    },
  },
}

export const DarkMode: Story = {
  args: baseArgs,
  decorators: [mapDecorator(building.geoCoords[1], building.geoCoords[0], true)],
  parameters: { backgrounds: { default: "dark" } },
}
