import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import {
  LayoutDashboard,
  Newspaper,
  CalendarRange,
  Calendar,
  Activity,
  Map as MapIcon,
} from "lucide-react"
import type { NavigationItem } from "@/config/navigation"
import { DesktopNav } from "./DesktopNav"

// Wave 198 SW4 — DesktopNav Storybook fixture (navbar family).
//
// Pure presentation: renders a <ul> of TanStack <Link>s from menuLinks; active
// state + scroll callbacks are all props (no router-derived state), so the story
// fully controls them. Ambient RouterProvider lets <Link to> render the anchors.
//
// Variants: Default / Compact (icon-only) / DarkMode.

const MENU: NavigationItem[] = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/news", label: "News", icon: Newspaper },
  { to: "/schedule", label: "Schedule", icon: CalendarRange },
  { to: "/events", label: "Events", icon: Calendar },
  { to: "/activity", label: "Activity", icon: Activity },
  { to: "/map", label: "Map", icon: MapIcon },
]

const noop = () => {}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <nav style={{ background: "var(--bg-page)", padding: "1.25rem 2rem", minHeight: 80 }}>
        <Story />
      </nav>
    </div>
  )
}

const meta: Meta<typeof DesktopNav> = {
  title: "Navbar/DesktopNav",
  component: DesktopNav,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
  args: {
    menuLinks: MENU,
    isActive: (to) => to === "/dashboard",
    isSameTarget: () => false,
    scrollToTop: noop,
    markScrollFromBottom: noop,
    prefersReducedMotion: false,
    isCompact: false,
  },
}

export default meta
type Story = StoryObj<typeof DesktopNav>

export const Default: Story = {
  decorators: [themed(false)],
}

export const Compact: Story = {
  args: { isCompact: true },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
