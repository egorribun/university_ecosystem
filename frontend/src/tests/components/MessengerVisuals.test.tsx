import { render, screen } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"
import { ContactList, ChatWindow } from "../../components/messenger"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"

// Mock translations
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

// Mock SmartImage
vi.mock("@/components/media/SmartImage", () => ({
  default: ({ alt, className }: { alt?: string; className?: string }) => (
    <img alt={alt} className={className} />
  ),
}))

const queryClient = new QueryClient()

describe("Messenger Visual Overhaul", () => {
  const mockContacts = [
    {
      id: "1",
      name: "John Doe",
      avatar: "",
      lastMessage: "Hello",
      lastMessageTime: "12:00",
      unread: 2,
      online: true,
    },
  ]

  it("ContactList should have premium container styles", () => {
    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <ContactList contacts={mockContacts} selectedId={null} onSelect={() => {}} />
      </QueryClientProvider>
    )

    const listContainer = container.firstChild as HTMLElement
    expect(listContainer.className).toContain("msg-sidebar-bg")
    expect(listContainer.className).toContain("custom-scrollbar")
  })

  it("ContactList items should have motion and premium styles", () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ContactList contacts={mockContacts} selectedId={null} onSelect={() => {}} />
      </QueryClientProvider>
    )

    const contactItem = screen.getByRole("button")
    // Wave 182 SW1 — refactored msg-contact-item → messenger-stagger-item
    // (the legacy class had no CSS rules; entrance animation lives in the
    // W181 SW1 .messenger-stagger-item utility).
    expect(contactItem.className).toContain("messenger-stagger-item")
    expect(contactItem.className).toContain("rounded-2xl")
  })

  it("ChatWindow should have virtualizer and relative positioning", () => {
    // Wave 183 SW5 — ChatWindow now renders a no-messages empty state when
    // messages.length === 0 (instead of an empty virtualizer container).
    // Pass at least one message to exercise the virtualizer branch this
    // test asserts on.
    const mockMessage = {
      id: "1",
      senderId: "user-1",
      senderName: "John",
      senderAvatar: "",
      text: "Hello",
      timestamp: "12:00",
      isMe: false,
      status: "sent" as const,
    }
    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <ChatWindow messages={[mockMessage]} />
      </QueryClientProvider>
    )

    // Wave 182 SW1 — refactored msg-chat-area → messenger-chat-area
    // (W181 SW1 convention; rule lives in tokens/messenger.css after the
    // .messenger-bubble-* / .messenger-active-chip section).
    const chatArea = container.querySelector(".messenger-chat-area")
    expect(chatArea).toBeTruthy()
    expect(chatArea?.className).toContain("overflow-y-auto")
  })

  it("ChatWindow should render no-messages empty state when messages array is empty", () => {
    // Wave 183 SW5 — verify empty state renders with role=log + aria-live
    // + the noMessages.title key from messenger.json.
    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <ChatWindow messages={[]} />
      </QueryClientProvider>
    )

    const chatArea = container.querySelector(".messenger-chat-area")
    expect(chatArea).toBeTruthy()
    expect(chatArea?.getAttribute("role")).toBe("log")
    expect(chatArea?.getAttribute("aria-live")).toBe("polite")
    expect(chatArea?.textContent).toContain("messenger:noMessages.title")
  })
})
