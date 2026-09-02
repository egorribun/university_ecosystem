import { render, screen, fireEvent, waitFor, act } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"
import type { Chat } from "@/api/chat"

/**
 * Wave 211 G4 (SW10) — GroupInfoPanel unit tests.
 *
 * The security-relevant UI logic is the kick-button gating (owner-only) +
 * the always-present leave action; rename is any-member. Mirrors NewChatModal's
 * mock strategy (i18n passthrough, SmartImage → img, useFocusTrap no-op, api
 * client mocked for the add-member search useQuery).
 */

const mocks = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock("@/components/media/SmartImage", () => ({
  default: ({ alt, className }: { alt?: string; className?: string }) => (
    <img alt={alt} className={className} />
  ),
}))

vi.mock("@/hooks/useFocusTrap", () => ({ default: () => ({ current: null }) }))

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>()
  return { ...actual, default: { get: mocks.apiGet } }
})

import { GroupInfoPanel } from "@/components/messenger/GroupInfoPanel"

const wrapper = ({ children }: { children: ReactNode }) => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}

const OWNER = "owner-id"
const MEMBER = "member-id"

const groupChat = (createdBy: string): Chat => ({
  id: "group-1",
  chat_type: "group",
  name: "Project Alpha",
  created_by: createdBy,
  participants: [
    { id: OWNER, full_name: "Olga Owner", avatar_url: null, is_active: true },
    { id: MEMBER, full_name: "Mike Member", avatar_url: null, is_active: false },
  ] as never,
  unread_count: 0,
  created_at: "2026-06-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z",
})

const baseProps = {
  open: true,
  onClose: vi.fn(),
  presenceMap: {},
  onRename: vi.fn(),
  onAddMember: vi.fn(),
  onRemoveMember: vi.fn(),
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.apiGet.mockResolvedValue({ data: [] })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("GroupInfoPanel (W211 G4)", () => {
  it("renders no panel when closed or when no group chat is selected", () => {
    const { rerender } = render(
      <GroupInfoPanel {...baseProps} open={false} chat={groupChat(OWNER)} currentUserId={OWNER} />,
      { wrapper }
    )
    expect(screen.queryByRole("dialog")).toBeNull()

    rerender(<GroupInfoPanel {...baseProps} open chat={null} currentUserId={OWNER} />)
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("renders the group name, member count + owner badge", () => {
    render(<GroupInfoPanel {...baseProps} chat={groupChat(OWNER)} currentUserId={OWNER} />, {
      wrapper,
    })
    expect(screen.getByRole("dialog")).toBeTruthy()
    expect(screen.getByText("Project Alpha")).toBeTruthy()
    // The owner row carries the owner badge.
    expect(screen.getByText("messenger:groupOwner")).toBeTruthy()
  })

  it("owner sees a kick affordance for OTHER members (not themselves, not the owner)", () => {
    render(<GroupInfoPanel {...baseProps} chat={groupChat(OWNER)} currentUserId={OWNER} />, {
      wrapper,
    })
    // Owner can remove Mike Member, but not themselves via a kick button (the
    // owner removes themselves via the always-present Leave action).
    expect(screen.getByRole("button", { name: "messenger:removeMember" })).toBeTruthy()
  })

  it("a non-owner member does NOT see kick buttons for others", () => {
    render(<GroupInfoPanel {...baseProps} chat={groupChat(OWNER)} currentUserId={MEMBER} />, {
      wrapper,
    })
    // No "Remove {name}" kick button (only the owner can kick); the member can
    // still self-leave (the leave action uses the leaveGroup label).
    expect(screen.queryByRole("button", { name: "messenger:removeMember" })).toBeNull()
  })

  it("leave action calls onRemoveMember with the current user id", () => {
    const onRemoveMember = vi.fn()
    render(
      <GroupInfoPanel
        {...baseProps}
        onRemoveMember={onRemoveMember}
        chat={groupChat(OWNER)}
        currentUserId={MEMBER}
      />,
      { wrapper }
    )
    // The footer Leave button (there may also be a self-leave row icon — both
    // call onRemoveMember(currentUserId)). Click the footer leave button.
    const leaveButtons = screen.getAllByRole("button", { name: "messenger:leaveGroup" })
    fireEvent.click(leaveButtons[leaveButtons.length - 1]!)
    expect(onRemoveMember).toHaveBeenCalledWith(MEMBER)
  })

  it("labels self, owner and presence states while exposing owner kick and self leave actions", () => {
    const onRemoveMember = vi.fn()
    render(
      <GroupInfoPanel
        {...baseProps}
        onRemoveMember={onRemoveMember}
        chat={groupChat(OWNER)}
        currentUserId={OWNER}
        presenceMap={{ [OWNER]: { active: true, last_seen_at: null } }}
      />,
      { wrapper }
    )

    const memberList = screen.getByRole("list", { name: /messenger:group.members/ })
    expect(screen.getByText("messenger:memberYou")).toBeInTheDocument()
    expect(screen.getByText("messenger:groupOwner")).toBeInTheDocument()
    expect(memberList.querySelectorAll(".messenger-online-indicator")).toHaveLength(1)

    fireEvent.click(screen.getByRole("button", { name: "messenger:removeMember" }))
    const leaveButtons = screen.getAllByRole("button", { name: "messenger:leaveGroup" })
    fireEvent.click(leaveButtons[leaveButtons.length - 1]!)
    expect(onRemoveMember).toHaveBeenNthCalledWith(1, MEMBER)
    expect(onRemoveMember).toHaveBeenNthCalledWith(2, OWNER)
  })

  it("uses an untitled fallback for blank group names and an empty member count", () => {
    const blankChat = { ...groupChat(OWNER), name: "   ", participants: [] as never }
    render(<GroupInfoPanel {...baseProps} chat={blankChat} currentUserId={OWNER} />, { wrapper })

    expect(screen.getByRole("heading", { name: "messenger:group.untitled" })).toBeInTheDocument()
    expect(screen.getByText("messenger:group.members")).toBeInTheDocument()
  })

  it("rename flow calls onRename with the trimmed new name", () => {
    const onRename = vi.fn()
    render(
      <GroupInfoPanel
        {...baseProps}
        onRename={onRename}
        chat={groupChat(OWNER)}
        currentUserId={OWNER}
      />,
      { wrapper }
    )
    fireEvent.click(screen.getByRole("button", { name: "messenger:renameGroup" }))
    const input = screen.getByRole("textbox", { name: "messenger:groupName" })
    fireEvent.change(input, { target: { value: "  Renamed Group  " } })
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.save" }))
    expect(onRename).toHaveBeenCalledWith("Renamed Group")
  })

  it("does not submit a blank rename and supports Escape cancellation", () => {
    const onRename = vi.fn()
    render(
      <GroupInfoPanel
        {...baseProps}
        onRename={onRename}
        chat={groupChat(OWNER)}
        currentUserId={OWNER}
      />,
      { wrapper }
    )
    fireEvent.click(screen.getByRole("button", { name: "messenger:renameGroup" }))
    const input = screen.getByRole("textbox", { name: "messenger:groupName" })
    const save = screen.getByRole("button", { name: "common:buttons.save" })
    fireEvent.change(input, { target: { value: "   " } })
    expect(save).toBeDisabled()
    fireEvent.keyDown(input, { key: "Escape" })
    expect(screen.queryByRole("textbox", { name: "messenger:groupName" })).toBeNull()
    expect(onRename).not.toHaveBeenCalled()
  })

  it("searches for addable users and filters existing members", async () => {
    mocks.apiGet.mockResolvedValueOnce({
      data: [
        { id: MEMBER, full_name: "Mike Member", avatar_url: null },
        { id: "new-user", full_name: "Nina New", avatar_url: "nina.png" },
      ],
    })
    const onAddMember = vi.fn()
    render(
      <GroupInfoPanel
        {...baseProps}
        onAddMember={onAddMember}
        chat={groupChat(OWNER)}
        currentUserId={OWNER}
      />,
      { wrapper }
    )

    fireEvent.click(screen.getByRole("button", { name: "messenger:addMember" }))
    const search = screen.getByRole("textbox", { name: "messenger:searchUsers" })
    fireEvent.change(search, { target: { value: "Nina" } })
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 250))
    })
    await waitFor(() => expect(mocks.apiGet).toHaveBeenCalledWith("/users?limit=10&search=Nina"))

    expect(screen.getByRole("button", { name: /Nina New/ })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Mike Member/ })).toBeNull()
    fireEvent.click(screen.getByRole("button", { name: /Nina New/ }))
    expect(onAddMember).toHaveBeenCalledWith("new-user")
  })

  it("resets transient rename and add-search state when closed", () => {
    const { rerender } = render(
      <GroupInfoPanel {...baseProps} chat={groupChat(OWNER)} currentUserId={OWNER} />,
      { wrapper }
    )
    fireEvent.click(screen.getByRole("button", { name: "messenger:renameGroup" }))
    expect(screen.getByRole("textbox", { name: "messenger:groupName" })).toBeInTheDocument()

    rerender(
      <GroupInfoPanel {...baseProps} open={false} chat={groupChat(OWNER)} currentUserId={OWNER} />
    )
    rerender(<GroupInfoPanel {...baseProps} open chat={groupChat(OWNER)} currentUserId={OWNER} />)
    expect(screen.queryByRole("textbox", { name: "messenger:groupName" })).toBeNull()
  })

  it("closes from the close button, backdrop and Escape", () => {
    const onClose = vi.fn()
    const { rerender } = render(
      <GroupInfoPanel
        {...baseProps}
        onClose={onClose}
        chat={groupChat(OWNER)}
        currentUserId={OWNER}
      />,
      { wrapper }
    )
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.close" }))
    fireEvent.keyDown(document, { key: "Escape" })
    fireEvent.click(screen.getAllByRole("presentation")[0]!)
    expect(onClose).toHaveBeenCalledTimes(3)

    rerender(
      <GroupInfoPanel
        {...baseProps}
        open={false}
        onClose={onClose}
        chat={groupChat(OWNER)}
        currentUserId={OWNER}
      />
    )
    fireEvent.keyDown(document, { key: "Escape" })
    expect(onClose).toHaveBeenCalledTimes(3)
  })
})
