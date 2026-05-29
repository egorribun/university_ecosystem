import { useRef } from "react"
import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import type { MapRef } from "react-map-gl/maplibre"
import MapLibreMapComponent from "./MapLibreMap"

// Wave 199 SW1 — MapLibreMap story (CONTEXT-tier, attempt-or-defer).
//
// The full MapLibre GL campus map. Unlike the W194 marker stories (which
// rendered their own <Map> with an empty offline style), MapLibreMap computes
// its mapStyle internally (remote OpenFreeMap tiles) and inits WebGL + the
// cinematic intro — so this story carries a remote-tile fetch + a real WebGL
// canvas. W194 proved maplibre WebGL inits in the real-Chrome Storybook iframe.
// Props are trivial (null selection + no-op handlers + a MapRef). Wrapped in
// `.map-theme` for the marker/popup tokens; sized container so the map fills it.
//
// If the wave-close runtime smoke shows a WebGL/remote-tile failure, this story
// is deferred to W200 per the plan (substitute-or-defer discipline).
//
// Variants: Default / DarkMode.

const MapHarness = ({ dark }: { dark: boolean }) => {
  const mapRef = useRef<MapRef | null>(null)
  return (
    <div style={{ width: 680, height: 460, position: "relative" }}>
      <MapLibreMapComponent
        selectedBuilding={null}
        activeCategory="all"
        highlightedBuilding={null}
        onSelectBuilding={() => {}}
        onDeselectBuilding={() => {}}
        mapRef={mapRef}
        isDark={dark}
        timePeriod="afternoon"
      />
    </div>
  )
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div className="map-theme" style={{ background: "var(--bg-page)", padding: "1.5rem" }}>
        <Story />
      </div>
    </div>
  )
}

const meta: Meta<typeof MapLibreMapComponent> = {
  title: "Map/MapLibreMap",
  component: MapLibreMapComponent,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof MapLibreMapComponent>

export const Default: Story = {
  render: () => <MapHarness dark={false} />,
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  render: () => <MapHarness dark={true} />,
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
