import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, it, vi } from "vitest"

import { MessengerSidebar } from "@/components/messenger/MessengerSidebar"
import type { Contact } from "@/components/messenger/types"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)

vi.mock("@tanstack/react-router", () => ({ useNavigate: () => vi.fn() }))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

it("returns focus to the search input after clearing the real contact list's empty results", async () => {
  const user = userEvent.setup()
  const contact: Contact = {
    id: "chat-1",
    name: "Study Group",
    avatar: "",
    lastMessage: "Class notes",
    lastMessageTime: "12:00",
    unread: 0,
    online: false,
  }
  const client = new QueryClient()
  render(
    <QueryClientProvider client={client}>
      <MessengerSidebar
        contacts={[contact]}
        isMobile={false}
        selectedChatId={null}
        setIsNewChatModalOpen={vi.fn()}
      />
    </QueryClientProvider>
  )

  const input = screen.getByRole("textbox")
  expect(screen.getByText("Study Group")).toBeInTheDocument()
  await user.type(input, "unmatched")
  expect(screen.queryByText("Study Group")).not.toBeInTheDocument()
  const clear = screen.getByRole("button", { name: "messenger:noChats.searchEmpty.clearSearch" })
  await user.tab()
  expect(clear).toHaveFocus()
  await user.keyboard("{Enter}")

  expect(clear).not.toBeInTheDocument()
  expect(screen.getByText("Study Group")).toBeInTheDocument()
  expect(input).toHaveValue("")
  expect(input).toHaveFocus()
  await user.keyboard("notes")
  expect(input).toHaveValue("notes")
  expect(screen.getByText("Study Group")).toBeInTheDocument()
})
