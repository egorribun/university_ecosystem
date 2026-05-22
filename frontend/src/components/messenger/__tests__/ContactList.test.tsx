import { render, screen, fireEvent } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"

import { ContactList } from "@/components/messenger/ContactList"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"

/**
 * Wave 183 SW12 — ContactList unit tests.
 *
 * Covers W183 SW1 + SW4 regression guards for ContactList behaviour beyond
 * the existing MessengerVisuals.test.tsx (which covers populated-list render
 * + className invariants).
 *
 * In-scope:
 *  - W183 SW1 empty state when contacts.length === 0 (with + without
 *    isSearchActive).
 *  - W183 SW1 "Start new conversation" CTA fires onStartNewChat.
 *  - W183 SW1 "Clear search" CTA fires onClearSearch.
 *  - W183 SW4 Arrow Up/Down/Home/End keyboard navigation between rows.
 *  - role="status" + aria-live="polite" on empty state.
 */

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts ? `${key}|${JSON.stringify(opts)}` : key,
  }),
}))

vi.mock("@/components/media/SmartImage", () => ({
  default: ({ alt }: { alt?: string }) => <img alt={alt} />,
}))

const queryClient = new QueryClient()

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
)

const mockContacts = [
  {
    id: "1",
    name: "Alice",
    avatar: "",
    lastMessage: "Hello",
    lastMessageTime: "12:00",
    unread: 0,
    online: true,
  },
  {
    id: "2",
    name: "Bob",
    avatar: "",
    lastMessage: "Hi there",
    lastMessageTime: "13:00",
    unread: 2,
    online: false,
  },
  {
    id: "3",
    name: "Carol",
    avatar: "",
    lastMessage: "Hey",
    lastMessageTime: "14:00",
    unread: 0,
    online: false,
  },
]

describe("ContactList — empty state (W183 SW1)", () => {
  it("renders no-chats empty state when contacts is empty and !isSearchActive", () => {
    render(<ContactList contacts={[]} selectedId={null} onSelect={() => {}} />, { wrapper })

    // Title key + description key visible
    expect(screen.getByText("messenger:noChats.title")).toBeTruthy()
    expect(screen.getByText("messenger:noChats.description")).toBeTruthy()
  })

  it("renders search-empty state when contacts is empty and isSearchActive", () => {
    render(
      <ContactList
        contacts={[]}
        selectedId={null}
        onSelect={() => {}}
        isSearchActive
        searchQuery="qwerty"
      />,
      { wrapper }
    )

    expect(screen.getByText("messenger:noChats.searchEmpty.title")).toBeTruthy()
    // Interpolation preserved — mock serializes opts as JSON
    expect(
      screen.getByText('messenger:noChats.searchEmpty.description|{"query":"qwerty"}')
    ).toBeTruthy()
  })

  it("'Start new conversation' CTA fires onStartNewChat", () => {
    const onStartNewChat = vi.fn()
    render(
      <ContactList
        contacts={[]}
        selectedId={null}
        onSelect={() => {}}
        onStartNewChat={onStartNewChat}
      />,
      { wrapper }
    )

    const cta = screen.getByRole("button", { name: /messenger:noChats.cta/ })
    fireEvent.click(cta)
    expect(onStartNewChat).toHaveBeenCalledTimes(1)
  })

  it("'Clear search' CTA fires onClearSearch (search-empty variant)", () => {
    const onClearSearch = vi.fn()
    render(
      <ContactList
        contacts={[]}
        selectedId={null}
        onSelect={() => {}}
        isSearchActive
        searchQuery="qwerty"
        onClearSearch={onClearSearch}
      />,
      { wrapper }
    )

    const cta = screen.getByRole("button", {
      name: /messenger:noChats.searchEmpty.clearSearch/,
    })
    fireEvent.click(cta)
    expect(onClearSearch).toHaveBeenCalledTimes(1)
  })

  it("empty state has role=status + aria-live=polite", () => {
    const { container } = render(
      <ContactList contacts={[]} selectedId={null} onSelect={() => {}} />,
      { wrapper }
    )

    const status = container.querySelector('[role="status"][aria-live="polite"]')
    expect(status).toBeTruthy()
  })
})

describe("ContactList — keyboard navigation (W183 SW4)", () => {
  it("ArrowDown focuses next contact row", () => {
    render(<ContactList contacts={mockContacts} selectedId={null} onSelect={() => {}} />, {
      wrapper,
    })

    const aliceRow = document.getElementById("messenger-contact-1")!
    const bobRow = document.getElementById("messenger-contact-2")!

    aliceRow.focus()
    expect(document.activeElement).toBe(aliceRow)

    fireEvent.keyDown(aliceRow, { key: "ArrowDown" })
    expect(document.activeElement).toBe(bobRow)
  })

  it("ArrowUp focuses previous contact row", () => {
    render(<ContactList contacts={mockContacts} selectedId={null} onSelect={() => {}} />, {
      wrapper,
    })

    const bobRow = document.getElementById("messenger-contact-2")!
    const aliceRow = document.getElementById("messenger-contact-1")!

    bobRow.focus()
    fireEvent.keyDown(bobRow, { key: "ArrowUp" })
    expect(document.activeElement).toBe(aliceRow)
  })

  it("Home jumps focus to first contact", () => {
    render(<ContactList contacts={mockContacts} selectedId={null} onSelect={() => {}} />, {
      wrapper,
    })

    const carolRow = document.getElementById("messenger-contact-3")!
    const aliceRow = document.getElementById("messenger-contact-1")!

    carolRow.focus()
    fireEvent.keyDown(carolRow, { key: "Home" })
    expect(document.activeElement).toBe(aliceRow)
  })

  it("End jumps focus to last contact", () => {
    render(<ContactList contacts={mockContacts} selectedId={null} onSelect={() => {}} />, {
      wrapper,
    })

    const aliceRow = document.getElementById("messenger-contact-1")!
    const carolRow = document.getElementById("messenger-contact-3")!

    aliceRow.focus()
    fireEvent.keyDown(aliceRow, { key: "End" })
    expect(document.activeElement).toBe(carolRow)
  })

  it("ArrowDown at last contact does NOT wrap around (Slack-style)", () => {
    render(<ContactList contacts={mockContacts} selectedId={null} onSelect={() => {}} />, {
      wrapper,
    })

    const carolRow = document.getElementById("messenger-contact-3")!

    carolRow.focus()
    fireEvent.keyDown(carolRow, { key: "ArrowDown" })
    expect(document.activeElement).toBe(carolRow) // stays on last
  })

  it("ArrowUp at first contact does NOT wrap around", () => {
    render(<ContactList contacts={mockContacts} selectedId={null} onSelect={() => {}} />, {
      wrapper,
    })

    const aliceRow = document.getElementById("messenger-contact-1")!

    aliceRow.focus()
    fireEvent.keyDown(aliceRow, { key: "ArrowUp" })
    expect(document.activeElement).toBe(aliceRow) // stays on first
  })

  it("Enter on a contact row fires onSelect", () => {
    const onSelect = vi.fn()
    render(<ContactList contacts={mockContacts} selectedId={null} onSelect={onSelect} />, {
      wrapper,
    })

    const bobRow = document.getElementById("messenger-contact-2")!

    fireEvent.keyDown(bobRow, { key: "Enter" })
    expect(onSelect).toHaveBeenCalledWith("2")
  })
})
