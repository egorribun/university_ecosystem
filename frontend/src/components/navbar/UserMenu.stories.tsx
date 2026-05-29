import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import type { ComponentProps } from "react"
import { LazyMotion, domAnimation } from "framer-motion"
import { useTranslation } from "react-i18next"
import { MessengerContext } from "@/contexts/MessengerContext"
import type { User } from "@/types/User"
import { UserMenu } from "./UserMenu"

// Wave 198 SW4 — UserMenu Storybook fixture (navbar family).
//
// Renders MessengerButton + NotificationsBell + avatar + name + settings gear.
// MessengerButton calls useMessenger() → decorator supplies a MessengerContext
// stub (W197 SW7); NotificationsBell uses the ambient QueryClient (degrades). The
// `t: (key)=>string` prop is supplied by a real-useTranslation harness (W195 SW4
// pattern, no fake cast). m.* subtree → LazyMotion.
//
// Variants: Default / Compact / Loading / DarkMode.

const USER = {
  id: "u1",
  full_name: "Alice Anderson",
  email: "alice@university.dev",
  avatar_url: null,
  role: "student",
} as unknown as User

const noop = () => {}

type HarnessProps = Omit<ComponentProps<typeof UserMenu>, "t">
function UserMenuHarness(props: HarnessProps) {
  const { t } = useTranslation(["navigation", "common"])
  return <UserMenu {...props} t={t} />
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <MessengerContext.Provider
        value={{
          unreadCount: 0,
          presenceMap: {},
          isConnected: true,
          sendTyping: () => {},
          sendRead: () => {},
          getTypingUsersForChat: () => [],
        }}
      >
        <div className={dark ? "dark" : undefined}>
          <nav style={{ background: "var(--bg-page)", padding: "1rem 2rem", minHeight: 80 }}>
            <Story />
          </nav>
        </div>
      </MessengerContext.Provider>
    </LazyMotion>
  )
}

const meta: Meta<typeof UserMenu> = {
  title: "Navbar/UserMenu",
  component: UserMenu,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof UserMenu>

export const Default: Story = {
  render: () => (
    <UserMenuHarness
      user={USER}
      isAuth
      loading={false}
      go={noop}
      isCompact={false}
      prefersReducedMotion={false}
    />
  ),
  decorators: [themed(false)],
}

export const Compact: Story = {
  render: () => (
    <UserMenuHarness
      user={USER}
      isAuth
      loading={false}
      go={noop}
      isCompact
      prefersReducedMotion={false}
    />
  ),
  decorators: [themed(false)],
}

export const Loading: Story = {
  render: () => (
    <UserMenuHarness
      user={null}
      isAuth
      loading
      go={noop}
      isCompact={false}
      prefersReducedMotion={false}
    />
  ),
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  render: () => (
    <UserMenuHarness
      user={USER}
      isAuth
      loading={false}
      go={noop}
      isCompact={false}
      prefersReducedMotion={false}
    />
  ),
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
