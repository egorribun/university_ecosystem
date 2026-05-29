import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { useRef } from "react"
import type { MapRef } from "react-map-gl/maplibre"
import { MapControls } from "./MapControls"

// Wave 197 SW3 — MapControls Storybook fixture (CONTEXT-tier, cheap).
//
// Map control panel (zoom / compass / pitch / fullscreen / recenter). Takes a
// `mapRef` and null-guards every call (`mapRef.current?.getMap()...`), so a story
// passes useRef<MapRef | null>(null) — buttons render, clicks no-op. No live
// <Map> ancestor needed (unlike the W194 marker stories). Labels via the global
// I18nextProvider; .map-control-panel tokens via the .map-theme scope.
//
// Variants: Default / DarkMode.

function ControlsHarness() {
  const mapRef = useRef<MapRef | null>(null)
  return <MapControls mapRef={mapRef} />
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div
        className="map-theme"
        style={{ background: "var(--bg-page)", padding: "2rem", minHeight: 320 }}
      >
        <Story />
      </div>
    </div>
  )
}

const meta: Meta<typeof MapControls> = {
  title: "Map/MapControls",
  component: MapControls,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof MapControls>

export const Default: Story = {
  render: () => <ControlsHarness />,
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  render: () => <ControlsHarness />,
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
