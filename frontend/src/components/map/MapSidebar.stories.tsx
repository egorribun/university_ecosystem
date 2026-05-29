import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { AppShellProvider } from "@/contexts/AppShellContext"
import { getCampusBuildings } from "@/data/campusBuildings"
import { MapSidebar } from "./MapSidebar"

// Wave 197 SW3 — MapSidebar Storybook fixture (CONTEXT-tier, medium).
//
// Building/room info panel with integrated floor selector (desktop: inline panel;
// mobile: bottom sheet). Fully prop-driven; `building`/`floor` props accept
// undefined, so a real building from getCampusBuildings("ru") drives it. Calls
// useAppShell() (setOverlayState) which throws without a provider, so the
// decorator wraps in the real <AppShellProvider> (state + browser-guarded scroll
// helpers — Storybook-safe). No framer-motion; no portal.
//
// Variants: Desktop (inline panel) / Mobile (bottom sheet) / DarkMode.

const BUILDING = getCampusBuildings("ru")[0]
const FLOOR = BUILDING?.floors[0]

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <AppShellProvider>
      <div className={dark ? "dark" : undefined}>
        <div
          className="map-theme"
          style={{ background: "var(--bg-page)", padding: "1rem", minHeight: 640 }}
        >
          <Story />
        </div>
      </div>
    </AppShellProvider>
  )
}

const meta: Meta<typeof MapSidebar> = {
  title: "Map/MapSidebar",
  component: MapSidebar,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
  args: {
    building: BUILDING,
    floor: FLOOR,
    selectedFloor: FLOOR?.floor ?? 1,
    selectedRoom: null,
    onFloorChange: () => {},
    onRoomClick: () => {},
    onClose: () => {},
  },
}

export default meta
type Story = StoryObj<typeof MapSidebar>

export const Desktop: Story = {
  args: { isMobile: false },
  decorators: [themed(false)],
}

export const Mobile: Story = {
  args: { isMobile: true },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { isMobile: false },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
