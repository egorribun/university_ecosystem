import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { MessengerContext } from "@/contexts/MessengerContext"
import MessengerButton from "./MessengerButton"

// Wave 198 SW4 — MessengerButton Storybook fixture (navbar action).
//
// Zero-prop nav button that calls useMessenger() for the unread badge, so the
// decorator supplies a MessengerContext.Provider stub (W197 SW7 pattern). Uses
// useNavigate (ambient Router) + an m.span badge (LazyMotion).
//
// Variants: Default (no unread) / WithUnread / DarkMode.

const themed = (dark: boolean, unreadCount = 0): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <MessengerContext.Provider
        value={{
          unreadCount,
          presenceMap: {},
          isConnected: true,
          sendTyping: () => {},
          sendRead: () => {},
          sendJoin: () => {},
          sendLeave: () => {},
          getTypingUsersForChat: () => [],
        }}
      >
        <div className={dark ? "dark" : undefined}>
          <div style={{ background: "var(--bg-page)", padding: "2.5rem", minHeight: 120 }}>
            <Story />
          </div>
        </div>
      </MessengerContext.Provider>
    </LazyMotion>
  )
}

const meta: Meta<typeof MessengerButton> = {
  title: "Layout/MessengerButton",
  component: MessengerButton,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof MessengerButton>

export const Default: Story = {
  decorators: [themed(false)],
}

export const WithUnread: Story = {
  decorators: [themed(false, 5)],
}

export const DarkMode: Story = {
  decorators: [themed(true, 3)],
  parameters: { backgrounds: { default: "dark" } },
}
