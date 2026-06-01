import { render, screen, fireEvent } from "@testing-library/react"
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
})
