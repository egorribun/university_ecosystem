import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import type { ComponentProps } from "react"
import { LazyMotion, domAnimation } from "framer-motion"
import { MessengerContext } from "@/contexts/MessengerContext"
import type { Chat } from "@/api/chat"
import type { User } from "@/types/User"
import type { Message } from "./types"
import { ChatArea } from "./ChatArea"

// Wave 197 SW7 — ChatArea Storybook fixture (CONTEXT-tier, medium-hard).
//
// Full chat panel: header + ChatWindow (virtualized) + MessageInput +
// TypingIndicator. Calls useMessenger() (getTypingUsersForChat), so the decorator
// provides a tsc-typed MessengerContext.Provider stub (MessengerContext is
// exported in W197 SW7 for this — additive, unused-by-app, tree-shaken). The m.*
// tree needs <LazyMotion features={domAnimation}>. Fixtures reuse the W189
// ChatArea.test.tsx shapes; the decorator gives the virtualizer a real height.
//
// Variants: Conversation / Empty (no chat selected) / DarkMode.

const makeUser = (id: string, full_name: string): User =>
  ({ id, full_name, avatar_url: "" }) as unknown as User

const ACTIVE_CHAT: Chat = {
  id: "chat-1",
  participants: [makeUser("user-me", "Me"), makeUser("user-alice", "Alice Anderson")],
  unread_count: 0,
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-20T12:00:00Z",
} as Chat

const MESSAGES: Message[] = [
  {
    id: "m1",
    text: "Hey, how are you?",
    senderId: "user-alice",
    senderName: "Alice",
    senderAvatar: "",
    timestamp: "12:00",
    isMe: false,
  },
  {
    id: "m2",
    text: "Doing great — shipping the Storybook coverage batch!",
    senderId: "user-me",
    senderName: "Me",
    senderAvatar: "",
    timestamp: "12:01",
    isMe: true,
    status: "read",
  },
  {
    id: "m3",
    text: "Nice. Any blockers?",
    senderId: "user-alice",
    senderName: "Alice",
    senderAvatar: "",
    timestamp: "12:02",
    isMe: false,
  },
  {
    id: "m4",
    text: "All green. 👋",
    senderId: "user-me",
    senderName: "Me",
    senderAvatar: "",
    timestamp: "12:03",
    isMe: true,
    status: "sent",
  },
]

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
          sendJoin: () => {},
          sendLeave: () => {},
          getTypingUsersForChat: () => [],
        }}
      >
        <div className={dark ? "dark" : undefined}>
          <div
            className="messenger-theme bg-msg-chat"
            style={{ height: 640, width: "100%", maxWidth: 900 }}
          >
            <Story />
          </div>
        </div>
      </MessengerContext.Provider>
    </LazyMotion>
  )
}

const noop = () => {}

const meta: Meta<typeof ChatArea> = {
  title: "Messenger/ChatArea",
  component: ChatArea,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
  args: {
    isMobile: false,
    selectedChatId: "chat-1",
    activeChat: ACTIVE_CHAT,
    // Message[] from ./types is structurally identical to the source's UiMessage
    // shape; cast mirrors the W189 ChatArea.test.tsx `as ChatAreaProps` pattern.
    messages: MESSAGES as ComponentProps<typeof ChatArea>["messages"],
    messagesLoading: false,
    messagesError: false,
    onRetryMessages: noop,
    showSearchInChat: false,
    setShowSearchInChat: noop,
    searchQuery: "",
    setSearchQuery: noop,
    showChatMenu: false,
    setShowChatMenu: noop,
    handleSendMessage: noop,
    handleViewProfile: noop,
    handleClearChat: noop,
    handleDeleteChat: noop,
    getOtherParticipant: (chat) => chat.participants.find((p) => p.id !== "user-me"),
    presenceMap: { "user-alice": { active: true, last_seen_at: null } },
  },
}

export default meta
type Story = StoryObj<typeof ChatArea>

export const Conversation: Story = {
  decorators: [themed(false)],
}

export const Empty: Story = {
  args: { selectedChatId: null, activeChat: null, messages: [] },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
