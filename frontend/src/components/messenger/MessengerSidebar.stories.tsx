import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import type { Contact } from "./types"
import { MessengerSidebar } from "./MessengerSidebar"

// Wave 197 SW7 — MessengerSidebar Storybook fixture (CONTEXT-tier, medium).
//
// Sidebar = search + new-chat button + ContactList. Does NOT call useMessenger()
// (only useMessengerController as a type for `contacts`), so no context stub is
// needed — just <LazyMotion features={domAnimation}> for the m.* sidebar
// transitions + .messenger-theme + a Contact[] fixture (reused from the W192
// ContactList story).
//
// Variants: Default / Mobile / DarkMode.

const CONTACTS: Contact[] = [
  {
    id: "1",
    name: "Alice",
    avatar: "",
    lastMessage: "Hello! How are you doing today?",
    lastMessageTime: "12:00",
    unread: 0,
    online: true,
  },
  {
    id: "2",
    name: "Bob",
    avatar: "",
    lastMessage: "Hi there — got a minute to chat?",
    lastMessageTime: "13:00",
    unread: 2,
    online: false,
  },
  {
    id: "3",
    name: "Carol",
    avatar: "",
    lastMessage: "Hey, schedule review is set for tomorrow.",
    lastMessageTime: "14:00",
    unread: 0,
    online: false,
  },
  {
    id: "4",
    name: "David",
    avatar: "",
    lastMessage: "Pushed the polish pass — all CI green ✓",
    lastMessageTime: "Yesterday",
    unread: 5,
    online: true,
  },
]

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div
          className="messenger-theme"
          style={{ background: "var(--bg-page)", height: 640, width: 360 }}
        >
          <Story />
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof MessengerSidebar> = {
  title: "Messenger/MessengerSidebar",
  component: MessengerSidebar,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
  args: {
    isMobile: false,
    contacts: CONTACTS,
    selectedChatId: "1",
    setIsNewChatModalOpen: () => {},
  },
}

export default meta
type Story = StoryObj<typeof MessengerSidebar>

export const Default: Story = {
  decorators: [themed(false)],
}

export const Mobile: Story = {
  args: { isMobile: true },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
