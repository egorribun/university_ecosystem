import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { AppShellProvider } from "@/contexts/AppShellContext"
import { MessengerContext } from "@/contexts/MessengerContext"
import Navbar from "./Navbar"

// Wave 199 SW1 — Navbar integration story (CONTEXT-tier, no infra).
//
// Zero-prop sticky navbar. Drives itself entirely from ambient providers:
// useNavbarLogic + useNavbarMorph read useAuth (mock admin via preview.tsx
// AuthContext), useRouterState (preview RouterProvider, pathname "/"), and i18n.
// useNavbarMorph → useScrollBehavior → useAppShell, so the real <AppShellProvider>
// is needed (W197 MapSidebar precedent). At the preview iframe width (<1350px
// breakpoints.wide) it renders the mobile actions row → MessengerButton calls
// useMessenger, so a MessengerContext.Provider stub is supplied (W198
// MessengerButton pattern). The NavbarLogo/NavbarActions/NavbarPill/MobileMenu
// sub-pieces are storied individually in W198. Uses framer-motion `m.*` →
// LazyMotion required.
//
// Variants: Default / DarkMode.

const MESSENGER_STUB = {
  unreadCount: 0,
  presenceMap: {},
  isConnected: true,
  sendTyping: () => {},
  sendJoin: () => {},
  sendLeave: () => {},
  getTypingUsersForChat: () => [],
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <AppShellProvider>
        <MessengerContext.Provider value={MESSENGER_STUB}>
          <div className={dark ? "dark" : undefined}>
            <div style={{ background: "var(--bg-page)", minHeight: 320 }}>
              <Story />
            </div>
          </div>
        </MessengerContext.Provider>
      </AppShellProvider>
    </LazyMotion>
  )
}

const meta: Meta<typeof Navbar> = {
  title: "Navbar/Navbar",
  component: Navbar,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof Navbar>

export const Default: Story = { decorators: [themed(false)] }

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
