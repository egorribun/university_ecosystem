import { act, fireEvent, render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { createElement, forwardRef, type ReactNode } from "react"
import type { Chat } from "@/api/chat"

const mocks = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock("@/components/media/SmartImage", () => ({
  default: ({ alt, className, srcRaw }: { alt?: string; className?: string; srcRaw?: string }) => (
    <img alt={alt} className={className} src={srcRaw} />
  ),
}))

vi.mock("@/hooks/useDebounced", () => ({
  useDebounced: (value: unknown) => value,
}))

vi.mock("@/hooks/useMediaQuery", () => ({
  default: () => false,
}))

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>()
  return { ...actual, default: { get: mocks.apiGet } }
})

// Preserve the actual DOM ref for the real focus-trap hook.
vi.mock("framer-motion", () => {
  const MotionDiv = forwardRef<HTMLElement, Record<string, unknown> & { children?: ReactNode }>(
    ({ children, ...props }, ref) => {
      const { initial, animate, exit, transition, ...domProps } = props
      return createElement(
        "div",
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
  MotionDiv.displayName = "MotionDiv"
  return {
    AnimatePresence: ({ children }: { children?: ReactNode }) => <>{children}</>,
    m: { div: MotionDiv },
  }
})

import { GroupInfoPanel } from "@/components/messenger/GroupInfoPanel"

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

describe("GroupInfoPanel real focus-trap Escape regression", () => {
  it("cancels inline rename on Escape without closing, while panel Escape still closes once", () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const onClose = vi.fn()
    const { unmount } = render(
      <QueryClientProvider client={queryClient}>
        <GroupInfoPanel
          {...baseProps}
          onClose={onClose}
          chat={groupChat(OWNER)}
          currentUserId={OWNER}
        />
      </QueryClientProvider>
    )

    const expectTabTrapped = () => {
      const tab = new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true })
      act(() => {
        screen.getByRole("dialog").dispatchEvent(tab)
      })
      // JSDOM trap contract, not a real-browser tab-order claim.
      expect(tab.defaultPrevented).toBe(true)
    }

    try {
      fireEvent.click(screen.getByRole("button", { name: "messenger:renameGroup" }))
      const editor = screen.getByRole("textbox", { name: "messenger:groupName" })
      fireEvent.change(editor, { target: { value: "Discarded" } })
      fireEvent.keyDown(editor, { key: "Escape" })

      expect(onClose).not.toHaveBeenCalled()
      expect(baseProps.onRename).not.toHaveBeenCalled()
      expect(screen.queryByRole("textbox", { name: "messenger:groupName" })).not.toBeInTheDocument()
      expect(screen.getByRole("dialog")).toBeInTheDocument()
      expectTabTrapped()

      fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" })
      expect(onClose).toHaveBeenCalledTimes(1)
    } finally {
      unmount()
      queryClient.clear()
    }
  })
})
