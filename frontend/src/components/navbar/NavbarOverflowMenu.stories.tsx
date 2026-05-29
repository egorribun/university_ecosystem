import type { Decorator, Meta, StoryObj } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { Home, Newspaper, Calendar, Map as MapIcon } from "lucide-react"
import { NavbarOverflowMenu } from "./NavbarOverflowMenu"
import type { NavigationItem } from "@/config/navigation"

const items: NavigationItem[] = [
  { to: "/dashboard", label: "Dashboard", icon: Home },
  { to: "/news", label: "News", icon: Newspaper },
  { to: "/events", label: "Events", icon: Calendar },
  { to: "/map", label: "Map", icon: MapIcon },
]

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div
          style={{
            background: "var(--bg-page)",
            padding: "2rem",
            display: "flex",
            justifyContent: "center",
          }}
        >
          <Story />
        </div>
      </div>
    </LazyMotion>
  )
}

const baseArgs = {
  items,
  isActive: (to: string) => to === "/dashboard",
  go: () => {},
  prefersReducedMotion: false,
  isCompact: false,
}

const meta: Meta<typeof NavbarOverflowMenu> = {
  title: "Navbar/NavbarOverflowMenu",
  component: NavbarOverflowMenu,
  tags: ["autodocs"],
  parameters: { layout: "centered" },
}

export default meta
type Story = StoryObj<typeof NavbarOverflowMenu>

export const Default: Story = {
  args: baseArgs,
  decorators: [themed(false)],
  parameters: {
    docs: {
      description: { story: "Overflow trigger button (active glow); the menu opens on click." },
    },
  },
}

export const DarkMode: Story = {
  args: baseArgs,
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
