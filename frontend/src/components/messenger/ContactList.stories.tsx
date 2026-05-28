import type { Meta, StoryObj } from "@storybook/react-vite"
import { useState } from "react"
import { ContactList } from "./ContactList"
import type { Contact } from "./types"

// Wave 192 SW3 — ContactList Storybook fixture.
//
// Pattern source: `frontend/src/components/messenger/__tests__/ContactList.test.tsx`
// (W183 SW12 baseline) — reuses the proven Contact mock shape (id, name,
// avatar, lastMessage, lastMessageTime, unread, online). Note: Contact type
// (NOT Chat) lives at `frontend/src/components/messenger/types.ts` (W192
// Phase 3 verification corrected plan's initial type-naming drift per
// W141 anti-pattern #3 vindication #110). The `api/chat.ts` `Chat` type is
// the server-side shape; ContactList uses the local component-mapped
// `Contact` shape.
//
// Variants:
//   • Empty — `contacts: []` + `isSearchActive: false`. Renders W183 SW1
//     "No conversations yet" empty state with MessagesSquare icon +
//     "Start new conversation" CTA.
//   • WithContacts — 5 mock contacts with varied state (online/offline,
//     read/unread badges). Demonstrates the W181 SW3 visual polish (active
//     row .messenger-active-chip + entrance stagger via @starting-style).
//     Includes interactive selection (useState for selectedId).
//   • SearchEmpty — `contacts: []` + `isSearchActive: true` +
//     `searchQuery: "qwerty"`. Renders W183 SW1 search-empty variant with
//     SearchX icon + interpolated query + "Clear search" CTA.
//   • Loading — `isLoading: true` renders 6 skeleton rows (h-[60px] matching
//     real ContactRow dimensions per W184 SW2; uses `.messenger-skeleton`
//     shimmer class from W181 SW1). Prevents the W183 SW1 empty state
//     flash during initial chats fetch.
//   • WithError — `isError: true` + `onRetry` callback renders W184 SW3
//     fetch-failure empty state with TriangleAlert + Retry CTA.
//   • DarkMode — standard dark-theme wrapper (Footer.stories.tsx pattern).

const mockContacts: Contact[] = [
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
    lastMessage: "Pushed W191 polish-v1 — all CI green ✓",
    lastMessageTime: "Yesterday",
    unread: 5,
    online: true,
  },
  {
    id: "5",
    name: "Erin",
    avatar: "",
    lastMessage: "Thanks for the doc handoff!",
    lastMessageTime: "Mon",
    unread: 0,
    online: false,
  },
]

const meta: Meta<typeof ContactList> = {
  title: "Messenger/ContactList",
  component: ContactList,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
  decorators: [
    (Story) => (
      <div
        className="flex flex-col bg-msg-sidebar"
        style={{ width: 360, height: 600, overflow: "auto" }}
      >
        <Story />
      </div>
    ),
  ],
}

export default meta
type Story = StoryObj<typeof ContactList>

export const Empty: Story = {
  args: {
    contacts: [],
    selectedId: null,
    onSelect: () => {},
    isSearchActive: false,
    isLoading: false,
    isError: false,
    onStartNewChat: () => {},
  },
  parameters: {
    docs: {
      description: {
        story:
          "Renders W183 SW1 'No conversations yet' empty state with MessagesSquare icon + violet 'Start new conversation' CTA. User-reported W183 issue #1 fix.",
      },
    },
  },
}

export const WithContacts: Story = {
  render: (args) => {
    const [selectedId, setSelectedId] = useState<string | null>("1")
    return <ContactList {...args} selectedId={selectedId} onSelect={(id) => setSelectedId(id)} />
  },
  args: {
    contacts: mockContacts,
    selectedId: "1",
    onSelect: () => {},
    isSearchActive: false,
    isLoading: false,
    isError: false,
  },
  parameters: {
    docs: {
      description: {
        story:
          "5 mock contacts with varied state. Active row (Alice) uses `.messenger-active-chip` left accent stripe per W181 SW3. Click any row to update selectedId via local useState — exercises the onSelect callback path.",
      },
    },
  },
}

export const SearchEmpty: Story = {
  args: {
    contacts: [],
    selectedId: null,
    onSelect: () => {},
    isSearchActive: true,
    searchQuery: "qwerty",
    isLoading: false,
    isError: false,
    onClearSearch: () => {},
  },
  parameters: {
    docs: {
      description: {
        story:
          "When user has typed a query that filters to zero contacts, the search-empty variant renders with SearchX icon + interpolated query text + 'Clear search' CTA. Mirrors ChatWindow's search-empty pattern (W184 SW1).",
      },
    },
  },
}

export const Loading: Story = {
  args: {
    contacts: [],
    selectedId: null,
    onSelect: () => {},
    isSearchActive: false,
    isLoading: true,
    isError: false,
  },
  parameters: {
    docs: {
      description: {
        story:
          "Renders 6 skeleton rows (h-[60px] matching real ContactRow dimensions per W184 SW2). Uses `.messenger-skeleton` shimmer class from W181 SW1. Branch order: isLoading takes priority over contacts.length === 0.",
      },
    },
  },
}

export const WithError: Story = {
  args: {
    contacts: [],
    selectedId: null,
    onSelect: () => {},
    isSearchActive: false,
    isLoading: false,
    isError: true,
    onRetry: () => {},
  },
  parameters: {
    docs: {
      description: {
        story:
          "W184 SW3 fetch-failure empty state with TriangleAlert + i18n description + Retry CTA. Branch order: isError takes priority over no-contacts-yet (W184 plan branch-order priority).",
      },
    },
  },
}

export const DarkMode: Story = {
  render: (args) => {
    const [selectedId, setSelectedId] = useState<string | null>("1")
    return <ContactList {...args} selectedId={selectedId} onSelect={(id) => setSelectedId(id)} />
  },
  args: {
    contacts: mockContacts,
    selectedId: "1",
    onSelect: () => {},
    isSearchActive: false,
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
