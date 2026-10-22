import { StrictMode, useState } from "react"
import type { ComponentProps, ReactNode } from "react"
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { LazyMotion, domAnimation } from "framer-motion"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ChatArea } from "@/components/messenger/ChatArea"
import type { Chat } from "@/api/chat"

type FocusRouteState = { location: { state: { messengerOpenedFromList: boolean } } }

const state = vi.hoisted(() => ({ reduced: false }))

vi.mock("@/hooks/useMediaQuery", () => ({
  default: () => state.reduced,
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock("@tanstack/react-router", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@tanstack/react-router")>()

  return {
    ...actual,
    useNavigate: () => vi.fn(),
    useRouter: () => ({ history: { back: vi.fn() } }),
    useRouterState: <T,>({ select }: { select: (value: FocusRouteState) => T }) =>
      select({
        location: { state: { messengerOpenedFromList: false } },
      }),
  }
})

vi.mock("@/contexts/MessengerContext", () => ({
  useMessenger: () => ({
    getTypingUsersForChat: () => [],
    sendTyping: vi.fn(),
  }),
}))

vi.mock("@/components/media/SmartImage", () => ({
  default: ({ alt }: { alt?: string }) => <img alt={alt} />,
}))

vi.mock("@/components/messenger", () => ({
  ChatWindow: () => null,
  MessageInput: () => null,
  TypingIndicator: () => null,
}))

const chat: Chat = {
  id: "chat-1",
  participants: [],
  unread_count: 0,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
}

const baseProps: ComponentProps<typeof ChatArea> = {
  isMobile: false,
  selectedChatId: chat.id,
  activeChat: chat,
  messages: [],
  showSearchInChat: false,
  setShowSearchInChat: vi.fn(),
  searchQuery: "",
  setSearchQuery: vi.fn(),
  showChatMenu: false,
  setShowChatMenu: vi.fn(),
  handleSendMessage: vi.fn(),
  handleViewProfile: vi.fn(),
  handleClearChat: vi.fn(),
  handleDeleteChat: vi.fn(),
  getOtherParticipant: () => undefined,
  presenceMap: {},
}

function Harness({
  selected = true,
  initiallySearching = false,
}: {
  selected?: boolean
  initiallySearching?: boolean
}) {
  const [showSearchInChat, setShowSearchInChat] = useState(initiallySearching)
  const [searchQuery, setSearchQuery] = useState("")

  return (
    <>
      <button type="button" aria-label="Outside chat" />
      <ChatArea
        {...baseProps}
        selectedChatId={selected ? chat.id : null}
        activeChat={selected ? chat : null}
        showSearchInChat={showSearchInChat}
        setShowSearchInChat={setShowSearchInChat}
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
      />
    </>
  )
}

function wrapper({ children }: { children: ReactNode }) {
  return (
    <StrictMode>
      <LazyMotion features={domAnimation}>{children}</LazyMotion>
    </StrictMode>
  )
}

const searchName = "messenger:searchMessages"

async function settledSearchToggle() {
  const toggle = await screen.findByRole("button", { name: searchName })
  const header = toggle.closest(".z-deep")

  expect(header).not.toBeNull()
  await waitFor(() => expect(header).toHaveStyle({ opacity: "1" }))
  return toggle
}

async function nextTwoFrames() {
  await act(async () => {
    await new Promise<void>((resolve) => {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => resolve())
      })
    })
  })
}

afterEach(() => {
  state.reduced = false
})

describe("ChatArea search focus across real presence transitions", () => {
  it.each([false, true])(
    "focuses the delayed input on open and reopen, reduced motion=%s",
    async (reduced) => {
      state.reduced = reduced
      render(<Harness />, { wrapper })

      const toggle = await settledSearchToggle()
      fireEvent.click(toggle)

      // Exercise the real wait-mode lifecycle, not synchronous replacement.
      expect(toggle).toBeInTheDocument()
      expect(screen.queryByRole("textbox", { name: searchName })).toBeNull()

      const input = await screen.findByRole("textbox", { name: searchName })
      await waitFor(() => expect(input).toHaveFocus())
      expect(toggle).not.toBeInTheDocument()

      fireEvent.click(screen.getByRole("button", { name: "common:buttons.close" }))
      const reopenedToggle = await settledSearchToggle()
      expect(input).not.toBeInTheDocument()

      fireEvent.click(reopenedToggle)
      expect(reopenedToggle).toBeInTheDocument()
      expect(screen.queryByRole("textbox", { name: searchName })).toBeNull()

      const reopenedInput = await screen.findByRole("textbox", { name: searchName })
      expect(reopenedInput).not.toBe(input)
      await waitFor(() => expect(reopenedInput).toHaveFocus())
    }
  )

  it("focuses an input that mounts after a chat becomes available", async () => {
    const { rerender } = render(<Harness selected={false} initiallySearching />, {
      wrapper,
    })

    expect(screen.queryByRole("textbox", { name: searchName })).toBeNull()

    rerender(<Harness initiallySearching />)

    const input = await screen.findByRole("textbox", { name: searchName })
    await waitFor(() => expect(input).toHaveFocus())
  })

  it("does not steal focus on a query-only rerender", async () => {
    render(<Harness initiallySearching />, { wrapper })

    const input = screen.getByRole("textbox", { name: searchName })
    await waitFor(() => expect(input).toHaveFocus())

    const outside = screen.getByRole("button", { name: "Outside chat" })
    outside.focus()
    expect(outside).toHaveFocus()

    fireEvent.change(input, { target: { value: "needle" } })
    expect(input).toHaveValue("needle")

    await nextTwoFrames()
    expect(outside).toHaveFocus()
  })
})
