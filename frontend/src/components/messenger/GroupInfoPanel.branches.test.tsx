import { render, screen, fireEvent, act, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { createElement, forwardRef, type ReactNode } from "react"
import type { Chat } from "@/api/chat"
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders"

/**
 * Sibling branch-coverage test for GroupInfoPanel (do NOT touch
 * GroupInfoPanel.test.tsx). The existing test covers the rename happy-path,
 * owner-kick gating, non-owner-no-kick, and the footer leave action. This file
 * fills the remaining uncovered statement / cold-branch lines:
 *  - Escape keydown → onClose (75-79) + the !open early-return guard (73)
 *  - the transient-state reset effect when the panel closes (86-90)
 *  - the add-member search UI: open search, type, cancel, no-results message,
 *    addable-result rows + onAddMember (102-110, 211-273)
 *  - the rename input Enter-saves / Escape-cancels keydown handler (178-180)
 *  - the empty-trimmed-name rename branch (113, 118)
 *  - the online presence indicator on a member row (310-314)
 *  - reduced-motion variant branch (138, 140-141)
 *  - the no-currentUserId leave guard (the && short-circuit)
 *
 * Mocks mirror GroupInfoPanel.test.tsx (i18n key passthrough, SmartImage → img,
 * useFocusTrap no-op, api client mocked). useDebounced is stubbed pass-through
 * so the add-member useQuery fires immediately (no fake timers needed).
 */

const mocks = vi.hoisted(() => ({
  apiGet: vi.fn(),
  focusTrap: vi.fn<(...args: [unknown]) => { current: null }>(() => ({ current: null })),
  debounced: vi.fn<(value: unknown, strategy?: unknown) => unknown>((value) => value),
  translation: vi.fn<(...args: unknown[]) => void>(),
  tCalls: vi.fn<(...args: unknown[]) => void>(),
  mediaQuery: vi.fn<(query: string) => boolean>(),
  reducedMotion: false,
}))

vi.mock("react-i18next", () => ({
  useTranslation: (...namespaces: unknown[]) => {
    mocks.translation(...namespaces)
    return {
      t: (key: string, opts?: Record<string, unknown>) => {
        mocks.tCalls(key, opts)
        return opts ? `${key}|${JSON.stringify(opts)}` : key
      },
    }
  },
}))

vi.mock("@/components/media/SmartImage", () => ({
  default: ({ alt, className, srcRaw }: { alt?: string; className?: string; srcRaw?: string }) => (
    <img alt={alt} className={className} src={srcRaw} />
  ),
}))

vi.mock("@/hooks/useFocusTrap", () => ({
  default: (options: unknown) => {
    mocks.focusTrap(options)
    return { current: null }
  },
}))

// Pass-through debounce so the add-member useQuery fires synchronously once the
// search input has > 1 char (no 300ms wait / fake timers).
vi.mock("@/hooks/useDebounced", () => ({
  useDebounced: (value: unknown, strategy?: unknown) => {
    mocks.debounced(value, strategy)
    return value
  },
}))

vi.mock("@/hooks/useMediaQuery", () => ({
  default: (query: string) => {
    mocks.mediaQuery(query)
    return mocks.reducedMotion
  },
}))

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>()
  return { ...actual, default: { get: mocks.apiGet } }
})

vi.mock("framer-motion", () => {
  const motionComponent = (Tag: "div") => {
    const Component = forwardRef<HTMLElement, Record<string, unknown> & { children?: ReactNode }>(
      ({ children, ...props }, ref) => {
        const { initial, animate, exit, transition, ...domProps } = props
        return createElement(
          Tag,
          {
            ...domProps,
            ref,
            "data-motion-initial": initial === undefined ? undefined : JSON.stringify(initial),
            "data-motion-animate": animate === undefined ? undefined : JSON.stringify(animate),
            "data-motion-exit": exit === undefined ? undefined : JSON.stringify(exit),
            "data-motion-transition":
              transition === undefined ? undefined : JSON.stringify(transition),
          },
          children as ReactNode
        )
      }
    )
    Component.displayName = `Motion(${Tag})`
    return Component
  }
  const motionProxy = { div: motionComponent("div") }
  return {
    AnimatePresence: ({ children }: { children?: ReactNode }) => <>{children}</>,
    m: motionProxy,
    motion: motionProxy,
  }
})

import { GroupInfoPanel } from "@/components/messenger/GroupInfoPanel"

let latestQueryClient: QueryClient | undefined
const wrapper = ({ children }: { children: ReactNode }) => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  latestQueryClient = queryClient
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
  mocks.reducedMotion = false
  latestQueryClient = undefined
  mocks.apiGet.mockResolvedValue({ data: [] })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("GroupInfoPanel branch coverage (W211 G4)", () => {
  it("Escape keydown invokes onClose (effect handler 75-79)", () => {
    const onClose = vi.fn()
    render(<GroupInfoPanel {...baseProps} onClose={onClose} chat={groupChat(OWNER)} />, {
      wrapper,
    })
    fireEvent.keyDown(document, { key: "Escape" })
    expect(onClose).toHaveBeenCalledTimes(1)
    // A non-Escape key takes the cold branch and does NOT close.
    fireEvent.keyDown(document, { key: "Enter" })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it("does NOT bind the keydown handler / renders nothing when closed (73 early-return)", () => {
    const onClose = vi.fn()
    render(
      <GroupInfoPanel {...baseProps} open={false} onClose={onClose} chat={groupChat(OWNER)} />,
      {
        wrapper,
      }
    )
    // The AnimatePresence body is gated on `open && chat` — closed = no dialog.
    expect(screen.queryByRole("dialog")).toBeNull()
    // The effect early-returns on !open, so the keydown listener isn't attached.
    fireEvent.keyDown(document, { key: "Escape" })
    expect(onClose).not.toHaveBeenCalled()
  })

  it("renders nothing when chat is null even though open is true (124 guard)", () => {
    render(<GroupInfoPanel {...baseProps} chat={null} />, { wrapper })
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("preserves translation, reduced-motion, focus-trap, and dialog motion contracts", () => {
    const onClose = vi.fn()
    render(
      <GroupInfoPanel
        {...baseProps}
        onClose={onClose}
        chat={groupChat(OWNER)}
        currentUserId={OWNER}
      />,
      { wrapper }
    )

    expect(mocks.translation).toHaveBeenCalledWith(["messenger", "common"])
    expect(mocks.mediaQuery).toHaveBeenCalledWith("(prefers-reduced-motion: reduce)")
    expect(mocks.debounced).toHaveBeenCalledWith("", "search")
    expect(mocks.focusTrap).toHaveBeenCalledWith(
      expect.objectContaining({
        active: true,
        initialFocus: false,
        returnFocus: true,
        onDeactivate: onClose,
      })
    )

    const backdrop = screen.getAllByRole("presentation")[0]!
    expect(backdrop).toHaveAttribute("data-motion-initial", JSON.stringify({ opacity: 0 }))
    expect(backdrop).toHaveAttribute("data-motion-animate", JSON.stringify({ opacity: 1 }))
    expect(backdrop).toHaveAttribute("data-motion-exit", JSON.stringify({ opacity: 0 }))

    const dialog = screen.getByRole("dialog")
    expect(dialog).toHaveAttribute(
      "data-motion-initial",
      JSON.stringify({ opacity: 0, scale: 0.92, y: 20 })
    )
    expect(dialog).toHaveAttribute(
      "data-motion-animate",
      JSON.stringify({ scale: 1, opacity: 1, y: 0 })
    )
    expect(dialog).toHaveAttribute(
      "data-motion-exit",
      JSON.stringify({ scale: 0.92, opacity: 0, y: 20 })
    )
    expect(dialog).not.toHaveAttribute("data-motion-transition")
    expect(screen.getByRole("list")).toHaveAttribute(
      "aria-label",
      'messenger:group.members|{"count":2}'
    )
    expect(mocks.tCalls).toHaveBeenCalledWith("messenger:group.members", { count: 2 })
    expect(mocks.tCalls).toHaveBeenCalledWith("messenger:removeMember", { name: "Mike Member" })
  })

  it("uses empty participants safely when the chat omits its member collection", () => {
    const chat = { ...groupChat(OWNER), participants: undefined } as never as Chat
    render(<GroupInfoPanel {...baseProps} chat={chat} currentUserId={OWNER} />, { wrapper })
    expect(screen.getByRole("list")).toHaveAttribute(
      "aria-label",
      'messenger:group.members|{"count":0}'
    )
    expect(screen.getByText('messenger:group.members|{"count":0}')).toBeInTheDocument()
  })

  it("resets transient sub-state when the panel transitions open → closed (86-90)", () => {
    const { rerender } = render(<GroupInfoPanel {...baseProps} chat={groupChat(OWNER)} />, {
      wrapper,
    })
    // Enter the rename-editing sub-state so the reset effect has something to undo.
    fireEvent.click(screen.getByRole("button", { name: "messenger:renameGroup" }))
    expect(screen.getByRole("textbox", { name: "messenger:groupName" })).toBeTruthy()

    // Close — the reset effect (open === false branch) clears editing state.
    rerender(<GroupInfoPanel {...baseProps} open={false} chat={groupChat(OWNER)} />)
    expect(screen.queryByRole("dialog")).toBeNull()

    // Re-open: the rename input is gone (state was reset to !isEditingName).
    rerender(<GroupInfoPanel {...baseProps} open chat={groupChat(OWNER)} />)
    expect(screen.queryByRole("textbox", { name: "messenger:groupName" })).toBeNull()
    expect(screen.getByRole("button", { name: "messenger:renameGroup" })).toBeTruthy()
  })

  it("backdrop click + dialog stopPropagation (onClick handlers)", () => {
    const onClose = vi.fn()
    render(<GroupInfoPanel {...baseProps} onClose={onClose} chat={groupChat(OWNER)} />, {
      wrapper,
    })
    // Clicking the dialog itself stops propagation → does NOT close.
    fireEvent.click(screen.getByRole("dialog"))
    expect(onClose).not.toHaveBeenCalled()
    // Clicking the backdrop (the outermost role=presentation wrapper) closes.
    const backdrops = screen.getAllByRole("presentation")
    fireEvent.click(backdrops[0]!)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it("rename input Enter saves the trimmed name (178)", () => {
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
    fireEvent.change(input, { target: { value: "  Via Enter  " } })
    fireEvent.keyDown(input, { key: "Enter" })
    expect(onRename).toHaveBeenCalledWith("Via Enter")
    // Editing closes after a save.
    expect(screen.queryByRole("textbox", { name: "messenger:groupName" })).toBeNull()
  })

  it("rename input Escape cancels editing without calling onRename (179)", () => {
    const onRename = vi.fn()
    render(<GroupInfoPanel {...baseProps} onRename={onRename} chat={groupChat(OWNER)} />, {
      wrapper,
    })
    fireEvent.click(screen.getByRole("button", { name: "messenger:renameGroup" }))
    const input = screen.getByRole("textbox", { name: "messenger:groupName" })
    fireEvent.change(input, { target: { value: "Discarded" } })
    fireEvent.keyDown(input, { key: "Escape" })
    expect(onRename).not.toHaveBeenCalled()
    expect(screen.queryByRole("textbox", { name: "messenger:groupName" })).toBeNull()
  })

  it("rename input ignores other keys (cold keydown branch)", () => {
    const onRename = vi.fn()
    render(<GroupInfoPanel {...baseProps} onRename={onRename} chat={groupChat(OWNER)} />, {
      wrapper,
    })
    fireEvent.click(screen.getByRole("button", { name: "messenger:renameGroup" }))
    const input = screen.getByRole("textbox", { name: "messenger:groupName" })
    fireEvent.change(input, { target: { value: "Typing" } })
    fireEvent.keyDown(input, { key: "a" })
    expect(onRename).not.toHaveBeenCalled()
    // Still editing.
    expect(screen.getByRole("textbox", { name: "messenger:groupName" })).toBeTruthy()
  })

  it("saving an empty/whitespace name does NOT call onRename but exits editing (113 + 118 cold branch)", () => {
    const onRename = vi.fn()
    // A group whose name is null → startRename seeds an empty draft (113 ??).
    const chat = { ...groupChat(OWNER), name: null } as Chat
    render(<GroupInfoPanel {...baseProps} onRename={onRename} chat={chat} />, { wrapper })
    fireEvent.click(screen.getByRole("button", { name: "messenger:renameGroup" }))
    const input = screen.getByRole("textbox", { name: "messenger:groupName" })
    expect(input).toHaveValue("")
    fireEvent.change(input, { target: { value: "   " } })
    fireEvent.keyDown(input, { key: "Enter" })
    expect(onRename).not.toHaveBeenCalled()
    expect(screen.queryByRole("textbox", { name: "messenger:groupName" })).toBeNull()
  })

  it("falls back to the untitled label when the group has no name (151 cold branch)", () => {
    const chat = { ...groupChat(OWNER), name: "   " } as Chat
    render(<GroupInfoPanel {...baseProps} chat={chat} />, { wrapper })
    expect(screen.getByText("messenger:group.untitled")).toBeTruthy()
  })

  describe("add-member search flow (211-273)", () => {
    it("opens search, fetches, lists addable (non-member) results + invokes onAddMember", async () => {
      const onAddMember = vi.fn()
      mocks.apiGet.mockResolvedValue({
        data: [
          { id: "new-user", full_name: "Nina Newbie", avatar_url: null, is_active: true },
          // Already a member → filtered out by addableResults (110).
          { id: MEMBER, full_name: "Mike Member", avatar_url: null, is_active: false },
        ],
      })
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
      const searchInput = screen.getByRole("textbox", { name: "messenger:searchUsers" })
      await act(async () => {
        fireEvent.change(searchInput, { target: { value: "Ni" } })
      })

      await waitFor(() => {
        expect(mocks.apiGet).toHaveBeenCalledWith("/users?limit=10&search=Ni")
      })
      await waitFor(() => {
        expect(latestQueryClient?.getQueryData(["users", "Ni"])).toEqual([
          { id: "new-user", full_name: "Nina Newbie", avatar_url: null, is_active: true },
          { id: MEMBER, full_name: "Mike Member", avatar_url: null, is_active: false },
        ])
      })

      // Addable row (the existing member is excluded).
      const addButton = await screen.findByRole("button", { name: /Nina Newbie/ })
      expect(screen.queryByText("Mike Member")).toBeTruthy() // member list still has Mike
      expect(screen.queryByText("messenger:noUsersFound")).toBeNull()
      fireEvent.click(addButton)
      expect(onAddMember).toHaveBeenCalledWith("new-user")
    })

    it("shows the no-results message when the search has results but none are addable", async () => {
      // Only an existing member comes back → addableResults is empty.
      mocks.apiGet.mockResolvedValue({
        data: [{ id: MEMBER, full_name: "Mike Member", avatar_url: null, is_active: false }],
      })
      render(<GroupInfoPanel {...baseProps} chat={groupChat(OWNER)} currentUserId={OWNER} />, {
        wrapper,
      })
      fireEvent.click(screen.getByRole("button", { name: "messenger:addMember" }))
      const searchInput = screen.getByRole("textbox", { name: "messenger:searchUsers" })
      await act(async () => {
        fireEvent.change(searchInput, { target: { value: "Mi" } })
      })
      await waitFor(() => {
        expect(mocks.apiGet).toHaveBeenCalled()
      })
      expect(await screen.findByText("messenger:noUsersFound")).toBeTruthy()
    })

    it("does not show no-results for the one-character minimum search", () => {
      render(<GroupInfoPanel {...baseProps} chat={groupChat(OWNER)} currentUserId={OWNER} />, {
        wrapper,
      })
      fireEvent.click(screen.getByRole("button", { name: "messenger:addMember" }))
      fireEvent.change(screen.getByRole("textbox", { name: "messenger:searchUsers" }), {
        target: { value: "x" },
      })
      expect(screen.queryByText("messenger:noUsersFound")).toBeNull()
      expect(mocks.apiGet).not.toHaveBeenCalled()
    })

    it("keeps the no-results message hidden while a search request is pending", async () => {
      let resolveSearch: ((value: { data: never[] }) => void) | undefined
      mocks.apiGet.mockReturnValue(
        new Promise<{ data: never[] }>((resolve) => {
          resolveSearch = resolve
        })
      )
      render(<GroupInfoPanel {...baseProps} chat={groupChat(OWNER)} currentUserId={OWNER} />, {
        wrapper,
      })
      fireEvent.click(screen.getByRole("button", { name: "messenger:addMember" }))
      fireEvent.change(screen.getByRole("textbox", { name: "messenger:searchUsers" }), {
        target: { value: "ab" },
      })
      await waitFor(() => expect(mocks.apiGet).toHaveBeenCalled())
      expect(screen.queryByText("messenger:noUsersFound")).toBeNull()
      resolveSearch?.({ data: [] })
      expect(await screen.findByText("messenger:noUsersFound")).toBeInTheDocument()
    })

    it("does not render no-results when the response contains an addable user", async () => {
      mocks.apiGet.mockResolvedValue({
        data: [{ id: "new-user", full_name: "Nina Newbie", avatar_url: null, is_active: true }],
      })
      render(<GroupInfoPanel {...baseProps} chat={groupChat(OWNER)} currentUserId={OWNER} />, {
        wrapper,
      })
      fireEvent.click(screen.getByRole("button", { name: "messenger:addMember" }))
      fireEvent.change(screen.getByRole("textbox", { name: "messenger:searchUsers" }), {
        target: { value: "ab" },
      })
      expect(await screen.findByRole("button", { name: /Nina Newbie/ })).toBeInTheDocument()
      expect(screen.queryByText("messenger:noUsersFound")).toBeNull()
    })

    it("treats an undefined search response as an empty result list", async () => {
      mocks.apiGet.mockResolvedValue({ data: undefined })
      render(<GroupInfoPanel {...baseProps} chat={groupChat(OWNER)} currentUserId={OWNER} />, {
        wrapper,
      })
      fireEvent.click(screen.getByRole("button", { name: "messenger:addMember" }))
      fireEvent.change(screen.getByRole("textbox", { name: "messenger:searchUsers" }), {
        target: { value: "ab" },
      })
      expect(await screen.findByText("messenger:noUsersFound")).toBeInTheDocument()
    })

    it("does not fetch users before the add search is opened", async () => {
      render(<GroupInfoPanel {...baseProps} chat={groupChat(OWNER)} currentUserId={OWNER} />, {
        wrapper,
      })
      await act(async () => {})
      expect(mocks.apiGet).not.toHaveBeenCalled()
    })

    it("cancel button closes the search + clears the query without fetching (232-235)", () => {
      render(<GroupInfoPanel {...baseProps} chat={groupChat(OWNER)} />, { wrapper })
      fireEvent.click(screen.getByRole("button", { name: "messenger:addMember" }))
      const searchInput = screen.getByRole("textbox", { name: "messenger:searchUsers" })
      // Single char (length === MIN_SEARCH_LENGTH) keeps the query disabled (108 cold).
      fireEvent.change(searchInput, { target: { value: "x" } })
      expect(mocks.apiGet).not.toHaveBeenCalled()

      fireEvent.click(screen.getByRole("button", { name: "common:buttons.cancel" }))
      // Search closed → the add-member trigger button is back.
      expect(screen.getByRole("button", { name: "messenger:addMember" })).toBeTruthy()
      expect(screen.queryByRole("textbox", { name: "messenger:searchUsers" })).toBeNull()
    })
  })

  it("renders the online presence indicator for an active member (310-314)", () => {
    render(
      <GroupInfoPanel
        {...baseProps}
        chat={groupChat(OWNER)}
        currentUserId={MEMBER}
        presenceMap={{ [OWNER]: { active: true } as never }}
      />,
      { wrapper }
    )
    expect(document.querySelector(".messenger-online-indicator")).toBeTruthy()
  })

  it("omits the presence indicator when the member is offline (310 cold branch)", () => {
    render(
      <GroupInfoPanel
        {...baseProps}
        chat={groupChat(OWNER)}
        currentUserId={MEMBER}
        presenceMap={{ [OWNER]: { active: false } as never }}
      />,
      { wrapper }
    )
    expect(document.querySelector(".messenger-online-indicator")).toBeNull()
  })

  it("renders the reduced-motion variant (138 / 140-141 branches)", () => {
    mocks.reducedMotion = true
    render(<GroupInfoPanel {...baseProps} chat={groupChat(OWNER)} />, { wrapper })
    const dialog = screen.getByRole("dialog")
    expect(dialog).toHaveAttribute("data-motion-initial", "false")
    expect(dialog).toHaveAttribute("data-motion-exit", JSON.stringify({ opacity: 0 }))
    expect(dialog).toHaveAttribute("data-motion-transition", JSON.stringify({ duration: 0 }))
  })

  it("footer Leave is a no-op when currentUserId is undefined (361 && guard)", () => {
    const onRemoveMember = vi.fn()
    render(
      <GroupInfoPanel {...baseProps} onRemoveMember={onRemoveMember} chat={groupChat(OWNER)} />,
      { wrapper }
    )
    const leaveButtons = screen.getAllByRole("button", { name: "messenger:leaveGroup" })
    fireEvent.click(leaveButtons[leaveButtons.length - 1]!)
    // No currentUserId → the `currentUserId &&` short-circuits, onRemoveMember not called.
    expect(onRemoveMember).not.toHaveBeenCalled()
    expect(screen.queryByRole("button", { name: /messenger:removeMember/ })).toBeNull()
  })

  it("self-leave row icon calls onRemoveMember with the current user (canRemove isSelf branch)", () => {
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
    // The self-leave row uses the leaveGroup aria-label (LogOut icon). The footer
    // button shares the label, so grab the FIRST (the in-list self-leave row).
    const leaveButtons = screen.getAllByRole("button", { name: "messenger:leaveGroup" })
    fireEvent.click(leaveButtons[0]!)
    expect(onRemoveMember).toHaveBeenCalledWith(MEMBER)
  })

  it("keeps owner/member avatar sources and fallback semantics exact", () => {
    const chat = {
      ...groupChat(OWNER),
      participants: [
        { id: OWNER, full_name: "Olga Owner", avatar_url: "owner.png", is_active: true },
        { id: MEMBER, full_name: "Mike Member", avatar_url: null, is_active: false },
      ] as never,
    } as Chat
    const { container } = render(
      <GroupInfoPanel {...baseProps} chat={chat} currentUserId={OWNER} />,
      { wrapper }
    )

    const memberImages = container.querySelectorAll("img")
    expect(memberImages).toHaveLength(2)
    expect(memberImages[0]).toHaveAttribute("src", "owner.png")
    expect(memberImages[1]).toHaveAttribute("src", AVATAR_PLACEHOLDER_URL)
  })

  it("binds the documented translation, debounce, and focus-trap contracts", () => {
    const onClose = vi.fn()
    render(
      <GroupInfoPanel
        {...baseProps}
        onClose={onClose}
        chat={groupChat(OWNER)}
        currentUserId={OWNER}
      />,
      { wrapper }
    )

    expect(mocks.translation).toHaveBeenCalledWith(["messenger", "common"])
    expect(mocks.debounced).toHaveBeenCalledWith("", "search")
    expect(mocks.focusTrap).toHaveBeenCalledWith(
      expect.objectContaining({
        active: true,
        initialFocus: false,
        returnFocus: true,
        onDeactivate: onClose,
      })
    )

    const dialog = screen.getByRole("dialog", { name: "Project Alpha" })
    expect(dialog).toHaveAttribute("aria-modal", "true")
    expect(dialog).toHaveAccessibleName("Project Alpha")
  })

  it("removes Escape listeners and clears transient state after closing", () => {
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

    fireEvent.click(screen.getByRole("button", { name: "messenger:renameGroup" }))
    fireEvent.change(screen.getByRole("textbox", { name: "messenger:groupName" }), {
      target: { value: "stale draft" },
    })
    fireEvent.click(screen.getByRole("button", { name: "messenger:addMember" }))
    fireEvent.change(screen.getByRole("textbox", { name: "messenger:searchUsers" }), {
      target: { value: "stale search" },
    })

    rerender(
      <GroupInfoPanel {...baseProps} open={false} onClose={onClose} chat={groupChat(OWNER)} />
    )
    fireEvent.keyDown(document, { key: "Escape" })
    expect(onClose).not.toHaveBeenCalled()

    rerender(<GroupInfoPanel {...baseProps} open chat={groupChat(OWNER)} currentUserId={OWNER} />)
    expect(screen.queryByRole("textbox", { name: "messenger:groupName" })).toBeNull()
    expect(screen.queryByRole("textbox", { name: "messenger:searchUsers" })).toBeNull()
    expect(screen.getByRole("button", { name: "messenger:renameGroup" })).toBeTruthy()
    expect(screen.getByRole("button", { name: "messenger:addMember" })).toBeTruthy()

    fireEvent.click(screen.getByRole("button", { name: "messenger:addMember" }))
    expect(screen.getByRole("textbox", { name: "messenger:searchUsers" })).toHaveValue("")
  })

  it("keeps owner controls and member rows accessible with precise authorization labels", () => {
    const onRemoveMember = vi.fn()
    render(
      <GroupInfoPanel
        {...baseProps}
        onRemoveMember={onRemoveMember}
        chat={groupChat(OWNER)}
        currentUserId={OWNER}
      />,
      { wrapper }
    )

    const ownerRow = screen.getByText("Olga Owner").closest("li")
    const memberRow = screen.getByText("Mike Member").closest("li")
    expect(ownerRow).not.toBeNull()
    expect(memberRow).not.toBeNull()
    expect(ownerRow).toHaveTextContent("messenger:memberYou")
    expect(ownerRow).toHaveTextContent("messenger:groupOwner")
    expect(ownerRow?.querySelector('button[aria-label*="messenger:removeMember"]')).toBeNull()

    const kick = screen.getByRole("button", {
      name: 'messenger:removeMember|{"name":"Mike Member"}',
    })
    expect(kick.className).toContain("min-h-[44px]")
    expect(kick.className).toContain("min-w-[44px]")
    fireEvent.click(kick)
    expect(onRemoveMember).toHaveBeenCalledWith(MEMBER)
  })

  it("disables rename and add-member mutations while their requests are pending", async () => {
    const onRename = vi.fn()
    const onAddMember = vi.fn()
    mocks.apiGet.mockResolvedValue({
      data: [{ id: "new-user", full_name: "Nina Newbie", avatar_url: null, is_active: true }],
    })
    const { rerender } = render(
      <GroupInfoPanel
        {...baseProps}
        onRename={onRename}
        onAddMember={onAddMember}
        isRenaming
        isAddingMember
        chat={groupChat(OWNER)}
        currentUserId={OWNER}
      />,
      { wrapper }
    )

    fireEvent.click(screen.getByRole("button", { name: "messenger:renameGroup" }))
    const save = screen.getByRole("button", { name: "common:buttons.save" })
    fireEvent.change(screen.getByRole("textbox", { name: "messenger:groupName" }), {
      target: { value: "Renamed" },
    })
    expect(save).toBeDisabled()
    fireEvent.click(save)
    expect(onRename).not.toHaveBeenCalled()

    rerender(
      <GroupInfoPanel
        {...baseProps}
        onAddMember={onAddMember}
        isAddingMember
        chat={groupChat(OWNER)}
        currentUserId={OWNER}
      />
    )
    fireEvent.click(screen.getByRole("button", { name: "messenger:addMember" }))
    fireEvent.change(screen.getByRole("textbox", { name: "messenger:searchUsers" }), {
      target: { value: "Ni" },
    })
    const add = await screen.findByRole("button", { name: /Nina Newbie/ })
    expect(add).toBeDisabled()
    fireEvent.click(add)
    expect(onAddMember).not.toHaveBeenCalled()
  })

  it("encodes add-member search terms and preserves avatar fallback semantics", async () => {
    mocks.apiGet.mockResolvedValue({
      data: [{ id: "new-user", full_name: "Nina Newbie", avatar_url: null, is_active: true }],
    })
    render(<GroupInfoPanel {...baseProps} chat={groupChat(OWNER)} currentUserId={OWNER} />, {
      wrapper,
    })

    fireEvent.click(screen.getByRole("button", { name: "messenger:addMember" }))
    fireEvent.change(screen.getByRole("textbox", { name: "messenger:searchUsers" }), {
      target: { value: "A+B&C" },
    })
    await waitFor(() => {
      expect(mocks.apiGet).toHaveBeenCalledWith("/users?limit=10&search=A%2BB%26C")
    })
    const add = await screen.findByRole("button", { name: /Nina Newbie/ })
    expect(add.querySelector("img")).toHaveAttribute("src", AVATAR_PLACEHOLDER_URL)
  })

  it("does not show no-results feedback during loading, then shows it after an empty response", async () => {
    let resolveSearch: ((value: { data: never[] }) => void) | undefined
    mocks.apiGet.mockReturnValue(
      new Promise<{ data: never[] }>((resolve) => {
        resolveSearch = resolve
      })
    )
    render(<GroupInfoPanel {...baseProps} chat={groupChat(OWNER)} currentUserId={OWNER} />, {
      wrapper,
    })

    fireEvent.click(screen.getByRole("button", { name: "messenger:addMember" }))
    fireEvent.change(screen.getByRole("textbox", { name: "messenger:searchUsers" }), {
      target: { value: "ab" },
    })
    await waitFor(() => expect(mocks.apiGet).toHaveBeenCalled())
    expect(screen.queryByText("messenger:noUsersFound")).toBeNull()

    resolveSearch?.({ data: [] })
    expect(await screen.findByText("messenger:noUsersFound")).toBeTruthy()
  })
})
