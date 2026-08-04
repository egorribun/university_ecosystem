import { fireEvent, render, screen } from "@testing-library/react"
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
    ChatArea: (props: { onOpenGroupInfo?: () => void; onRetryMessages?: () => void }) => (
      <div data-testid="mock-chat-area">
        <button data-testid="mock-open-group-info" onClick={props.onOpenGroupInfo} />
        <button data-testid="mock-retry-messages" onClick={props.onRetryMessages} />
      </div>
    ),
    MessengerSidebar: (props: { onRetry?: () => void }) => (
      <div data-testid="mock-sidebar">
        <button data-testid="mock-retry-chats" onClick={props.onRetry} />
      </div>
    ),
    MessengerBackdrop: () => <div data-testid="mock-backdrop" />,
    NewChatModal: (props: {
      open?: boolean
      onClose?: () => void
      onSelect?: (userId: string) => void
    }) => (
      <div data-testid="mock-new-chat-modal" data-open={String(!!props.open)}>
        <button data-testid="mock-new-chat-close" onClick={props.onClose} />
        <button data-testid="mock-new-chat-select" onClick={() => props.onSelect?.("user-1")} />
      </div>
    ),
    // Wave 211 — ForwardModal + GroupInfoPanel mocked (GroupInfoPanel uses
    // useQuery for the add-member search → would need a QueryClientProvider).
    ForwardModal: (props: { open?: boolean; onClose?: () => void }) => (
      <div data-testid="mock-forward-modal" data-open={String(!!props.open)}>
        <button data-testid="mock-forward-close" onClick={props.onClose} />
      </div>
    ),
    GroupInfoPanel: (props: { open?: boolean; onClose?: () => void }) => (
      <div data-testid="mock-group-info-panel" data-open={String(!!props.open)}>
        <button data-testid="mock-group-info-close" onClick={props.onClose} />
      </div>
    ),
  }
})

vi.mock("@/components/messenger/ProfileModal", () => ({
  ProfileModal: (props: { onClose?: () => void }) => (
    <div data-testid="mock-profile-modal">
      <button data-testid="mock-profile-close" onClick={props.onClose} />
    </div>
  ),
}))

vi.mock("@/components/ui/ConfirmDialog", () => ({
  ConfirmDialog: (props: { open?: boolean; onConfirm?: () => void; onCancel?: () => void }) => (
    <div data-testid="mock-confirm-dialog" data-open={String(!!props.open)}>
      <button data-testid="mock-confirm" onClick={props.onConfirm} />
      <button data-testid="mock-cancel" onClick={props.onCancel} />
    </div>
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
  // Wave 211 SW6 — forward
  forwardSourceMessageId: null,
  handleStartForward: vi.fn(),
  handleCancelForward: vi.fn(),
  handleForwardToChat: vi.fn(),
  isForwarding: false,
  // Wave 211 G4 — group display (SW8) + create (SW9) + member mgmt (SW10)
  activeChatDisplay: null,
  handleCreateGroup: vi.fn(),
  isCreatingGroup: false,
  currentUserId: "current-user-id",
  showGroupInfo: false,
  setShowGroupInfo: vi.fn(),
  handleRenameGroup: vi.fn(),
  handleAddMember: vi.fn(),
  handleRemoveMember: vi.fn(),
  isRenamingGroup: false,
  isAddingMember: false,
  isRemovingMember: false,
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

  it("uses the reduced-motion disconnect transition", () => {
    mockUseMessenger.mockReturnValue({ isConnected: false })
    mockMediaQuery.mockImplementation((q: string) => q.includes("prefers-reduced-motion"))
    render(<MessengerFeature />)
    expect(screen.getByRole("status")).toBeTruthy()
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

  it("wires retry, modal, group-panel, and confirm callbacks", () => {
    const refetchChats = vi.fn()
    const refetchMessages = vi.fn()
    const setIsNewChatModalOpen = vi.fn()
    const handleCreateChat = vi.fn()
    const handleCloseProfile = vi.fn()
    const handleCancelForward = vi.fn()
    const setShowGroupInfo = vi.fn()
    const setConfirmDialog = vi.fn()
    const onConfirm = vi.fn()
    mockController.mockReturnValue(
      makeController({
        chatsError: true,
        refetchChats,
        messagesError: true,
        refetchMessages,
        isNewChatModalOpen: true,
        setIsNewChatModalOpen,
        handleCreateChat,
        profileUser: { id: "profile-1" },
        handleCloseProfile,
        forwardSourceMessageId: "message-1",
        handleCancelForward,
        showGroupInfo: true,
        activeChatDisplay: { isGroup: true },
        setShowGroupInfo,
        confirmDialog: { open: true, title: "Confirm", message: "Proceed", onConfirm },
        setConfirmDialog,
      })
    )

    render(<MessengerFeature />)
    fireEvent.click(screen.getByTestId("mock-retry-chats"))
    fireEvent.click(screen.getByTestId("mock-retry-messages"))
    fireEvent.click(screen.getByTestId("mock-new-chat-close"))
    fireEvent.click(screen.getByTestId("mock-new-chat-select"))
    fireEvent.click(screen.getByTestId("mock-profile-close"))
    fireEvent.click(screen.getByTestId("mock-forward-close"))
    fireEvent.click(screen.getByTestId("mock-open-group-info"))
    fireEvent.click(screen.getByTestId("mock-group-info-close"))
    fireEvent.click(screen.getByTestId("mock-confirm"))
    fireEvent.click(screen.getByTestId("mock-cancel"))

    expect(refetchChats).toHaveBeenCalledTimes(1)
    expect(refetchMessages).toHaveBeenCalledTimes(1)
    expect(setIsNewChatModalOpen).toHaveBeenCalledWith(false)
    expect(handleCreateChat).toHaveBeenCalledWith("user-1")
    expect(handleCloseProfile).toHaveBeenCalledTimes(1)
    expect(handleCancelForward).toHaveBeenCalledTimes(1)
    expect(setShowGroupInfo).toHaveBeenCalledWith(true)
    expect(setShowGroupInfo).toHaveBeenCalledWith(false)
    expect(onConfirm).toHaveBeenCalledTimes(1)
    expect(setConfirmDialog).toHaveBeenCalledWith(null)
  })
})
