import type { Meta, StoryObj } from "@storybook/react-vite"
import { ChatWindow } from "./ChatWindow"
import type { Message } from "./types"

// Wave 192 SW3 — ChatWindow Storybook fixture.
//
// Pattern source: `frontend/src/components/messenger/__tests__/ChatWindow.test.tsx`
// (W185 SW2 baseline) — reuses the proven Message mock shape (id, senderId,
// senderName, senderAvatar, text, timestamp, isMe, status, attachments). Note:
// Message type lives at `frontend/src/components/messenger/types.ts`, NOT
// `frontend/src/api/chat.ts` (W192 Phase 3 verification corrected the plan's
// initial path drift per W141 anti-pattern #3 vindication #110).
//
// CRITICAL — fixed `height: 600px` decorator: ChatWindow uses
// `useVirtualizer` from `@tanstack/react-virtual` per W184 SW1. The
// virtualizer needs the SCROLL CONTAINER to have a real measurable height
// to calculate virtual items. Without an explicit height parent, the
// virtualizer would measure 0 and render no rows. The ChatWindow test file
// works around this via `vi.mock("@tanstack/react-virtual")` in jsdom; in
// Storybook (real browser) we just provide a real-height parent.
//
// Variants:
//   • Empty — `messages: []` + no other flags. Renders the W183 SW5 "Say hi"
//     empty state.
//   • WithMessages — 6 mock messages alternating sent/received. Exercises
//     the virtualizer happy path with mixed isMe values.
//   • SearchActive — `searchQuery: "hello"` filters the mock messages to
//     those containing "hello" (case-insensitive substring per W184 SW1).
//     Note: `useDebounced("search", 200ms)` introduces ~200ms delay before
//     filter applies — acceptable for visual review.
//   • Loading — `isLoading: true` renders 6 skeleton bubbles (W184 SW2
//     pattern with `.messenger-skeleton` shimmer class). Exercises the
//     loading branch BEFORE messages.length === 0 check.
//   • WithError — `isError: true` + `onRetry` callback renders the W184
//     SW3 fetch-failure empty state with TriangleAlert + Retry CTA.
//     Distinguishes "new chat" from "network error".
//   • DarkMode — standard dark-theme wrapper (Footer.stories.tsx pattern).

const NOW = "12:00"

const makeMessage = (overrides: Partial<Message> & Pick<Message, "id" | "text">): Message => ({
  senderId: "user-1",
  senderName: "Alice",
  senderAvatar: "",
  timestamp: NOW,
  isMe: false,
  ...overrides,
})

const mockMessages: Message[] = [
  makeMessage({ id: "m1", text: "Hey, how are you?", isMe: false, senderName: "Alice" }),
  makeMessage({ id: "m2", text: "I'm doing great, thanks!", isMe: true, status: "read" }),
  makeMessage({
    id: "m3",
    text: "Did you finish the schedule export feature?",
    isMe: false,
    senderName: "Alice",
  }),
  makeMessage({
    id: "m4",
    text: "Yes, shipped W76 polish-pass last night.",
    isMe: true,
    status: "read",
  }),
  makeMessage({
    id: "m5",
    text: "Hello, just checking in — any blockers?",
    isMe: false,
    senderName: "Alice",
  }),
  makeMessage({
    id: "m6",
    text: "All good. Hello back! 👋",
    isMe: true,
    status: "sent",
  }),
]

const meta: Meta<typeof ChatWindow> = {
  title: "Messenger/ChatWindow",
  component: ChatWindow,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
  decorators: [
    (Story) => (
      <div
        className="flex flex-col bg-msg-chat"
        style={{ height: 600, width: "100%", maxWidth: 800 }}
      >
        <Story />
      </div>
    ),
  ],
}

export default meta
type Story = StoryObj<typeof ChatWindow>

export const Empty: Story = {
  args: {
    messages: [],
    searchQuery: "",
    isLoading: false,
    isError: false,
  },
}

export const WithMessages: Story = {
  args: {
    messages: mockMessages,
    searchQuery: "",
    isLoading: false,
    isError: false,
  },
}

export const SearchActive: Story = {
  args: {
    messages: mockMessages,
    searchQuery: "hello",
    isLoading: false,
    isError: false,
    onClearSearch: () => {},
  },
  parameters: {
    docs: {
      description: {
        story:
          "`searchQuery: 'hello'` filters to messages m5 + m6 (case-insensitive substring match). Note ~200ms debounce delay via `useDebounced` 'search' preset (PERF-23-04) before filter applies.",
      },
    },
  },
}

export const Loading: Story = {
  args: {
    messages: [],
    searchQuery: "",
    isLoading: true,
    isError: false,
  },
  parameters: {
    docs: {
      description: {
        story:
          "Renders 6 skeleton bubbles (alternating left/right alignment matching real bubble dimensions per W184 SW2). Branch order: isLoading takes priority over messages.length === 0.",
      },
    },
  },
}

export const WithError: Story = {
  args: {
    messages: [],
    searchQuery: "",
    isLoading: false,
    isError: true,
    onRetry: () => {},
  },
  parameters: {
    docs: {
      description: {
        story:
          "Renders W184 SW3 fetch-failure empty state with TriangleAlert + Retry CTA. Branch order: isError takes priority over isLoading + no-messages-yet (W185 SW2 branch-order priority tests).",
      },
    },
  },
}

export const DarkMode: Story = {
  args: {
    messages: mockMessages,
    searchQuery: "",
    isLoading: false,
    isError: false,
  },
  parameters: {
    backgrounds: { default: "dark" },
  },
  decorators: [
    (Story) => (
      <div className="dark">
        <Story />
      </div>
    ),
  ],
}
