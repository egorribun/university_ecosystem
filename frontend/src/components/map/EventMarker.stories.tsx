import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { Map } from "react-map-gl/maplibre"
import type { StyleSpecification } from "maplibre-gl"
import "maplibre-gl/dist/maplibre-gl.css"
import { EventMarker } from "./EventMarker"
import type { MapEvent } from "@/hooks/useMapEvents"

// Wave 194 SW4 — EventMarker Storybook fixture (MapLibre-in-Storybook proven by the
// BuildingMarker spike). Same minimal <Map> + empty offline style decorator.
// EventMarker is an amber <Marker anchor="bottom"> with a CalendarDays pin; its
// popup contains a TanStack <Link to="/events/$id"> which resolves against the
// global preview memory-router. Hand-crafted MapEvent mock. Coord gotcha
// FIX-100-01: event.geoCoords [lat,lng] → longitude={[1]} latitude={[0]}.
//
// Variants: Default (pin), PopupOpen (card + view-details Link), DarkMode.

const event: MapEvent = {
  id: "evt-open-day",
  title: "Open Day — Faculty of Management",
  startsAt: "2026-06-15T18:00:00Z",
  endsAt: "2026-06-15T20:00:00Z",
  buildingId: "ГУК",
  participantCount: 42,
  location: "ГУК, ауд. 305",
  geoCoords: [55.71405, 37.81165],
}

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

const meta: Meta<typeof EventMarker> = {
  title: "Map/EventMarker",
  component: EventMarker,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof EventMarker>

const decorators = [mapDecorator(event.geoCoords[1], event.geoCoords[0])]

export const Default: Story = {
  args: { event },
  decorators,
}

export const PopupOpen: Story = {
  args: { event, isPopupOpen: true },
  decorators,
  parameters: {
    docs: {
      description: {
        story:
          "Click popup — amber header + date/time + location + participant count + a client-side 'View details' Link to /events/$id.",
      },
    },
  },
}

export const DarkMode: Story = {
  args: { event },
  decorators: [mapDecorator(event.geoCoords[1], event.geoCoords[0], true)],
  parameters: { backgrounds: { default: "dark" } },
}
