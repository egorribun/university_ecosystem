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
vi.mock("@/components/SmartImage", () => ({
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
    expect(contactItem.className).toContain("msg-contact-item")
    expect(contactItem.className).toContain("rounded-2xl")
  })

  it("ChatWindow should have virtualizer and relative positioning", () => {
    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <ChatWindow messages={[]} />
      </QueryClientProvider>
    )

    const chatArea = container.querySelector(".msg-chat-area")
    expect(chatArea).toBeTruthy()
    expect(chatArea?.className).toContain("overflow-y-auto")
  })
})
