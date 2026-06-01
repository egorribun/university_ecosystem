import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { type ComponentProps, useRef } from "react"
import { LazyMotion, domAnimation } from "framer-motion"
import { LayoutDashboard, Newspaper, Calendar, CalendarRange, User as UserIcon } from "lucide-react"
import { AppShellProvider } from "@/contexts/AppShellContext"
import type { User } from "@/types/User"
import { MobileMenu } from "./MobileMenu"

// Wave 198 SW4 — MobileMenu Storybook fixture (navbar family, mobile drawer).
//
// Right-side drawer with profile card + quick actions + nav links. Calls
// useAppShell() (overlay/scroll-lock state) → decorator supplies the real,
// side-effect-free <AppShellProvider> (W197 MapSidebar pattern). Uses m.*/
// AnimatePresence (LazyMotion) + createPortal to document.body — the portal
// escapes the .dark scope, so this is a default-theme-only story (EventQrDialog
// pattern). drawerTrapRef supplied via a useRef harness.
//
// Variants: Default (authed, with profile card) / Guest (no profile card).

const USER = {
  id: "u1",
  full_name: "Alice Anderson",
  email: "alice@university.dev",
  avatar_url: null,
  role: "student",
} as unknown as User

const MENU = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/news", label: "News", icon: Newspaper },
  { to: "/schedule", label: "Schedule", icon: CalendarRange },
  { to: "/events", label: "Events", icon: Calendar },
  { to: "/profile", label: "Profile", icon: UserIcon },
]

const noop = () => {}

type HarnessProps = Omit<ComponentProps<typeof MobileMenu>, "drawerTrapRef">
function MobileMenuHarness(props: HarnessProps) {
  const ref = useRef<HTMLDivElement>(null)
  return <MobileMenu {...props} drawerTrapRef={ref} />
}

const themed: Decorator = (Story) => (
  <LazyMotion features={domAnimation}>
    <AppShellProvider>
      <div style={{ background: "var(--bg-page)", minHeight: 480 }}>
        <Story />
      </div>
    </AppShellProvider>
  </LazyMotion>
)

const meta: Meta<typeof MobileMenu> = {
  title: "Navbar/MobileMenu",
  component: MobileMenu,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
  decorators: [themed],
}

export default meta
type Story = StoryObj<typeof MobileMenu>

export const Default: Story = {
  render: () => (
    <MobileMenuHarness
      isOpen
      onClose={noop}
      menuLinks={MENU}
      isActive={(to) => to === "/dashboard"}
      go={noop}
      user={USER}
      isAuth
      prefersReducedMotion={false}
    />
  ),
}

export const Guest: Story = {
  render: () => (
    <MobileMenuHarness
      isOpen
      onClose={noop}
      menuLinks={MENU}
      isActive={() => false}
      go={noop}
      user={null}
      isAuth={false}
      prefersReducedMotion={false}
    />
  ),
}
