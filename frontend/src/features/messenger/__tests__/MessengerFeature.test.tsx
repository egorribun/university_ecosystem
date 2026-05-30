import { render, screen } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach } from "vitest"

import MessengerFeature from "@/features/messenger/MessengerFeature"

/**
 * Wave 202 SW7 — MessengerFeature orchestrator unit tests (the last of the 3
 * previously untested messenger wrappers). The orchestrator owns the
 * sidebar/chat-area pane logic + the W183 SW6 WebSocket-disconnect banner and
 * mounts the modals. Its data hook (useMessengerController, ~30 fields) +
 * useMessenger context + useMediaQuery are mocked via vi.hoisted (canonical
 * vitest pattern — factories may reference hoisted holders); child components
 * are stubbed so the test asserts orchestration, not child internals.
 */

const { mockController, mockUseMessenger, mockMediaQuery } = vi.hoisted(() => ({
  mockController: vi.fn(),
  mockUseMessenger: vi.fn(() => ({ isConnected: true })),
  mockMediaQuery: vi.fn((_q: string) => false),
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts ? `${key}|${JSON.stringify(opts)}` : key,
  }),
}))

vi.mock("@/hooks/features/useMessengerController", () => ({
  useMessengerController: () => mockController(),
}))

vi.mock("@/contexts/MessengerContext", () => ({
  useMessenger: () => mockUseMessenger(),
}))

vi.mock("@/hooks/useMediaQuery", () => ({
  default: (q: string) => mockMediaQuery(q),
}))

vi.mock("@/components/messenger", async () => {
  const actual =
    await vi.importActual<typeof import("@/components/messenger")>("@/components/messenger")
  return {
    ...actual,
    ChatArea: () => <div data-testid="mock-chat-area" />,
    MessengerSidebar: () => <div data-testid="mock-sidebar" />,
    MessengerBackdrop: () => <div data-testid="mock-backdrop" />,
    NewChatModal: (props: { open?: boolean }) => (
      <div data-testid="mock-new-chat-modal" data-open={String(!!props.open)} />
    ),
  }
})

vi.mock("@/components/messenger/ProfileModal", () => ({
  ProfileModal: () => <div data-testid="mock-profile-modal" />,
}))

vi.mock("@/components/ui/ConfirmDialog", () => ({
  ConfirmDialog: (props: { open?: boolean }) => (
    <div data-testid="mock-confirm-dialog" data-open={String(!!props.open)} />
  ),
}))

// Controller fixture — provides every field MessengerFeature destructures.
// vi.fn() handlers; null/empty data by default. Override per test.
const makeController = (overrides: Record<string, unknown> = {}) => ({
  selectedChatId: null,
  activeChat: null,
  isNewChatModalOpen: false,
  setIsNewChatModalOpen: vi.fn(),
  showSearchInChat: false,
  setShowSearchInChat: vi.fn(),
  searchQuery: "",
  setSearchQuery: vi.fn(),
  showChatMenu: false,
  setShowChatMenu: vi.fn(),
  contacts: [],
  messages: [],
  chatsLoading: false,
  messagesLoading: false,
  chatsError: false,
  refetchChats: vi.fn(),
  messagesError: false,
  refetchMessages: vi.fn(),
  profileUser: null,
  isProfileLoading: false,
  profileError: false,
  handleViewProfile: vi.fn(),
  handleCloseProfile: vi.fn(),
  getOtherParticipant: vi.fn(() => null),
  presenceMap: {},
  confirmDialog: null,
  setConfirmDialog: vi.fn(),
  handleSendMessage: vi.fn(),
  handleCreateChat: vi.fn(),
  handleClearChat: vi.fn(),
  handleDeleteChat: vi.fn(),
  ...overrides,
})

beforeEach(() => {
  mockController.mockReturnValue(makeController())
  mockUseMessenger.mockReturnValue({ isConnected: true })
  mockMediaQuery.mockReturnValue(false)
})

describe("MessengerFeature", () => {
  it("renders sidebar + chat area + backdrop on desktop", () => {
    render(<MessengerFeature />)
    expect(screen.getByTestId("mock-sidebar")).toBeTruthy()
    expect(screen.getByTestId("mock-chat-area")).toBeTruthy()
    expect(screen.getByTestId("mock-backdrop")).toBeTruthy()
  })

  it("always mounts the new-chat modal, profile modal, and confirm dialog", () => {
    render(<MessengerFeature />)
    expect(screen.getByTestId("mock-new-chat-modal")).toBeTruthy()
    expect(screen.getByTestId("mock-profile-modal")).toBeTruthy()
    expect(screen.getByTestId("mock-confirm-dialog")).toBeTruthy()
  })

  it("shows the WS-disconnect banner (role=status) when the socket is disconnected", () => {
    mockUseMessenger.mockReturnValue({ isConnected: false })
    render(<MessengerFeature />)
    expect(screen.getByText("messenger:connectionStatus.lost")).toBeTruthy()
    expect(screen.getByRole("status")).toBeTruthy()
  })

  it("hides the WS-disconnect banner when connected", () => {
    mockUseMessenger.mockReturnValue({ isConnected: true })
    render(<MessengerFeature />)
    expect(screen.queryByText("messenger:connectionStatus.lost")).toBeFalsy()
  })

  it("mobile + no chat selected → sidebar only (chat area hidden)", () => {
    mockMediaQuery.mockImplementation((q: string) => q.startsWith("(max-width"))
    mockController.mockReturnValue(makeController({ selectedChatId: null }))
    render(<MessengerFeature />)
    expect(screen.getByTestId("mock-sidebar")).toBeTruthy()
    expect(screen.queryByTestId("mock-chat-area")).toBeFalsy()
  })

  it("mobile + chat selected → chat area only (sidebar hidden)", () => {
    mockMediaQuery.mockImplementation((q: string) => q.startsWith("(max-width"))
    mockController.mockReturnValue(makeController({ selectedChatId: "chat-1" }))
    render(<MessengerFeature />)
    expect(screen.getByTestId("mock-chat-area")).toBeTruthy()
    expect(screen.queryByTestId("mock-sidebar")).toBeFalsy()
  })
})
