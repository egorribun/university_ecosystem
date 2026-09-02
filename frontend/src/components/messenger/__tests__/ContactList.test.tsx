import { render, screen, fireEvent } from "@testing-library/react"
import { afterEach, beforeEach, describe, it, expect, vi } from "vitest"

import { ContactList } from "@/components/messenger/ContactList"
import { GroupAvatar } from "@/components/messenger/GroupAvatar"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"

/**
 * Wave 183 SW12 — ContactList unit tests.
 *
 * Covers W183 SW1 + SW4 regression guards for ContactList behaviour beyond
 * the existing MessengerVisuals.test.tsx (which covers populated-list render
 * + className invariants).
 *
 * In-scope:
 *  - W183 SW1 empty state when contacts.length === 0 (with + without
 *    isSearchActive).
 *  - W183 SW1 "Start new conversation" CTA fires onStartNewChat.
 *  - W183 SW1 "Clear search" CTA fires onClearSearch.
 *  - W183 SW4 Arrow Up/Down/Home/End keyboard navigation between rows.
 *  - role="status" + aria-live="polite" on empty state.
 */

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts ? `${key}|${JSON.stringify(opts)}` : key,
  }),
}))

vi.mock("@/components/media/SmartImage", () => ({
  default: ({ alt, srcRaw, fallback }: { alt?: string; srcRaw?: string; fallback?: string }) => (
    <img alt={alt} src={srcRaw} data-fallback={fallback} />
  ),
}))

const { mockReducedMotion } = vi.hoisted(() => ({
  mockReducedMotion: vi.fn(() => false),
}))

vi.mock("@/hooks/useMediaQuery", () => ({
  default: () => mockReducedMotion(),
}))

const queryClient = new QueryClient()

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
)

afterEach(() => {
  mockReducedMotion.mockReturnValue(false)
})

const mockContacts = [
  {
    id: "1",
    name: "Alice",
    avatar: "",
    lastMessage: "Hello",
    lastMessageTime: "12:00",
    unread: 0,
    online: true,
  },
  {
    id: "2",
    name: "Bob",
    avatar: "",
    lastMessage: "Hi there",
    lastMessageTime: "13:00",
    unread: 2,
    online: false,
  },
  {
    id: "3",
    name: "Carol",
    avatar: "",
    lastMessage: "Hey",
    lastMessageTime: "14:00",
    unread: 0,
    online: false,
  },
]

describe("ContactList — empty state (W183 SW1)", () => {
  beforeEach(() => {
    mockReducedMotion.mockReturnValue(false)
  })

  it("renders no-chats empty state when contacts is empty and !isSearchActive", () => {
    render(<ContactList contacts={[]} selectedId={null} onSelect={() => {}} />, { wrapper })

    // Title key + description key visible
    expect(screen.getByText("messenger:noChats.title")).toBeTruthy()
    expect(screen.getByText("messenger:noChats.description")).toBeTruthy()
  })

  it("renders search-empty state when contacts is empty and isSearchActive", () => {
    render(
      <ContactList
        contacts={[]}
        selectedId={null}
        onSelect={() => {}}
        isSearchActive
        searchQuery="qwerty"
      />,
      { wrapper }
    )

    expect(screen.getByText("messenger:noChats.searchEmpty.title")).toBeTruthy()
    // Interpolation preserved — mock serializes opts as JSON
    expect(
      screen.getByText('messenger:noChats.searchEmpty.description|{"query":"qwerty"}')
    ).toBeTruthy()
  })

  it("'Start new conversation' CTA fires onStartNewChat", () => {
    const onStartNewChat = vi.fn()
    render(
      <ContactList
        contacts={[]}
        selectedId={null}
        onSelect={() => {}}
        onStartNewChat={onStartNewChat}
      />,
      { wrapper }
    )

    const cta = screen.getByRole("button", { name: /messenger:noChats.cta/ })
    fireEvent.click(cta)
    expect(onStartNewChat).toHaveBeenCalledTimes(1)
  })

  it("'Clear search' CTA fires onClearSearch (search-empty variant)", () => {
    const onClearSearch = vi.fn()
    render(
      <ContactList
        contacts={[]}
        selectedId={null}
        onSelect={() => {}}
        isSearchActive
        searchQuery="qwerty"
        onClearSearch={onClearSearch}
      />,
      { wrapper }
    )

    const cta = screen.getByRole("button", {
      name: /messenger:noChats.searchEmpty.clearSearch/,
    })
    fireEvent.click(cta)
    expect(onClearSearch).toHaveBeenCalledTimes(1)
  })

  it("omits the optional empty-state callbacks when they are not provided", () => {
    const { rerender } = render(
      <ContactList contacts={[]} selectedId={null} onSelect={() => {}} />,
      { wrapper }
    )
    expect(screen.queryByRole("button")).toBeFalsy()

    rerender(
      <ContactList
        contacts={[]}
        selectedId={null}
        onSelect={() => {}}
        isSearchActive
        searchQuery="missing"
      />
    )
    expect(screen.queryByRole("button")).toBeFalsy()
  })

  it("renders the animated error state without an optional retry callback", () => {
    render(<ContactList contacts={[]} selectedId={null} onSelect={() => {}} isError />, { wrapper })
    expect(screen.getByRole("alert")).toBeInTheDocument()
    expect(screen.queryByRole("button")).toBeFalsy()
  })

  it("empty state has role=status + aria-live=polite", () => {
    const { container } = render(
      <ContactList contacts={[]} selectedId={null} onSelect={() => {}} />,
      { wrapper }
    )

    const status = container.querySelector('[role="status"][aria-live="polite"]')
    expect(status).toBeTruthy()
  })

  it("uses reduced-motion transitions and omits the optional CTA", () => {
    mockReducedMotion.mockReturnValue(true)
    const { container } = render(
      <ContactList contacts={[]} selectedId={null} onSelect={() => {}} isSearchActive />,
      { wrapper }
    )

    expect(container.querySelector('[role="status"]')).toBeTruthy()
    expect(screen.queryByRole("button")).toBeFalsy()
  })

  it("keeps reduced-motion CTAs present without hover/tap animations", () => {
    mockReducedMotion.mockReturnValue(true)
    const onRetry = vi.fn()
    const onClearSearch = vi.fn()
    const onStartNewChat = vi.fn()

    const { rerender } = render(
      <ContactList contacts={[]} selectedId={null} onSelect={() => {}} isError onRetry={onRetry} />,
      { wrapper }
    )
    fireEvent.click(screen.getByRole("button", { name: /messenger:error.retry/ }))

    rerender(
      <ContactList
        contacts={[]}
        selectedId={null}
        onSelect={() => {}}
        isSearchActive
        onClearSearch={onClearSearch}
      />
    )
    fireEvent.click(
      screen.getByRole("button", { name: /messenger:noChats.searchEmpty.clearSearch/ })
    )

    rerender(
      <ContactList
        contacts={[]}
        selectedId={null}
        onSelect={() => {}}
        onStartNewChat={onStartNewChat}
      />
    )
    fireEvent.click(screen.getByRole("button", { name: /messenger:noChats.cta/ }))

    expect(onRetry).toHaveBeenCalledOnce()
    expect(onClearSearch).toHaveBeenCalledOnce()
    expect(onStartNewChat).toHaveBeenCalledOnce()
  })
})

describe("ContactList — keyboard navigation (W183 SW4)", () => {
  it("renders unread badges without entrance motion when reduced motion is enabled", () => {
    mockReducedMotion.mockReturnValue(true)
    render(<ContactList contacts={mockContacts} selectedId={null} onSelect={() => {}} />, {
      wrapper,
    })

    expect(screen.getByLabelText(/messenger:aria.unread/)).toHaveTextContent("2")
  })

  it("ArrowDown focuses next contact row", () => {
    render(<ContactList contacts={mockContacts} selectedId={null} onSelect={() => {}} />, {
      wrapper,
    })

    const aliceRow = document.getElementById("messenger-contact-1")!
    const bobRow = document.getElementById("messenger-contact-2")!

    aliceRow.focus()
    expect(document.activeElement).toBe(aliceRow)

    fireEvent.keyDown(aliceRow, { key: "ArrowDown" })
    expect(document.activeElement).toBe(bobRow)
  })

  it("ArrowUp focuses previous contact row", () => {
    render(<ContactList contacts={mockContacts} selectedId={null} onSelect={() => {}} />, {
      wrapper,
    })

    const bobRow = document.getElementById("messenger-contact-2")!
    const aliceRow = document.getElementById("messenger-contact-1")!

    bobRow.focus()
    fireEvent.keyDown(bobRow, { key: "ArrowUp" })
    expect(document.activeElement).toBe(aliceRow)
  })

  it("Home jumps focus to first contact", () => {
    render(<ContactList contacts={mockContacts} selectedId={null} onSelect={() => {}} />, {
      wrapper,
    })

    const carolRow = document.getElementById("messenger-contact-3")!
    const aliceRow = document.getElementById("messenger-contact-1")!

    carolRow.focus()
    fireEvent.keyDown(carolRow, { key: "Home" })
    expect(document.activeElement).toBe(aliceRow)
  })

  it("End jumps focus to last contact", () => {
    render(<ContactList contacts={mockContacts} selectedId={null} onSelect={() => {}} />, {
      wrapper,
    })

    const aliceRow = document.getElementById("messenger-contact-1")!
    const carolRow = document.getElementById("messenger-contact-3")!

    aliceRow.focus()
    fireEvent.keyDown(aliceRow, { key: "End" })
    expect(document.activeElement).toBe(carolRow)
  })

  it("leaves focus unchanged for an unrelated key", () => {
    render(<ContactList contacts={mockContacts} selectedId={null} onSelect={() => {}} />, {
      wrapper,
    })
    const aliceRow = document.getElementById("messenger-contact-1")!
    aliceRow.focus()

    fireEvent.keyDown(aliceRow, { key: "PageDown" })

    expect(document.activeElement).toBe(aliceRow)
  })

  it("ArrowDown at last contact does NOT wrap around (Slack-style)", () => {
    render(<ContactList contacts={mockContacts} selectedId={null} onSelect={() => {}} />, {
      wrapper,
    })

    const carolRow = document.getElementById("messenger-contact-3")!

    carolRow.focus()
    fireEvent.keyDown(carolRow, { key: "ArrowDown" })
    expect(document.activeElement).toBe(carolRow) // stays on last
  })

  it("ArrowUp at first contact does NOT wrap around", () => {
    render(<ContactList contacts={mockContacts} selectedId={null} onSelect={() => {}} />, {
      wrapper,
    })

    const aliceRow = document.getElementById("messenger-contact-1")!

    aliceRow.focus()
    fireEvent.keyDown(aliceRow, { key: "ArrowUp" })
    expect(document.activeElement).toBe(aliceRow) // stays on first
  })

  it("Enter on a contact row fires onSelect", () => {
    const onSelect = vi.fn()
    render(<ContactList contacts={mockContacts} selectedId={null} onSelect={onSelect} />, {
      wrapper,
    })

    const bobRow = document.getElementById("messenger-contact-2")!

    fireEvent.keyDown(bobRow, { key: "Enter" })
    expect(onSelect).toHaveBeenCalledWith("2")
  })
})

describe("ContactList — W184 SW2 skeleton + SW3 error states", () => {
  beforeEach(() => {
    mockReducedMotion.mockReturnValue(false)
  })

  it("renders 6 skeleton rows when isLoading=true (role=status + aria-live)", () => {
    const { container } = render(
      <ContactList contacts={[]} selectedId={null} onSelect={() => {}} isLoading />,
      { wrapper }
    )

    // role="status" + aria-live="polite" + i18n aria-label
    const statusEl = container.querySelector('[role="status"][aria-live="polite"]')
    expect(statusEl).toBeTruthy()
    expect(statusEl?.getAttribute("aria-label")).toBe("messenger:loading.contacts")

    // 6 skeleton rows per SKELETON_ROW_COUNT (each row has avatar circle + 2 text lines)
    const avatarSkeletons = container.querySelectorAll(".messenger-skeleton.size-12.rounded-full")
    expect(avatarSkeletons.length).toBe(6)

    // Each row has 2 text-line skeletons (title + subtitle) → 12 total .messenger-skeleton.h-X
    const titleSkeletons = container.querySelectorAll<HTMLDivElement>(".messenger-skeleton.h-3\\.5")
    const subtitleSkeletons = container.querySelectorAll<HTMLDivElement>(".messenger-skeleton.h-3")
    expect(titleSkeletons.length).toBe(6)
    expect(subtitleSkeletons.length).toBe(6)
  })

  it("skeleton width jitter follows deterministic formulas", () => {
    const { container } = render(
      <ContactList contacts={[]} selectedId={null} onSelect={() => {}} isLoading />,
      { wrapper }
    )

    // Title line: 65 + ((idx * 11) % 25)%
    const titleSkeletons = container.querySelectorAll<HTMLDivElement>(".messenger-skeleton.h-3\\.5")
    titleSkeletons.forEach((el, idx) => {
      const expectedTitleWidth = 65 + ((idx * 11) % 25)
      expect(el.style.width).toBe(`${expectedTitleWidth}%`)
    })

    // Subtitle line: 45 + ((idx * 7) % 35)%
    const subtitleSkeletons = container.querySelectorAll<HTMLDivElement>(".messenger-skeleton.h-3")
    subtitleSkeletons.forEach((el, idx) => {
      const expectedSubtitleWidth = 45 + ((idx * 7) % 35)
      expect(el.style.width).toBe(`${expectedSubtitleWidth}%`)
    })
  })

  it("renders TriangleAlert + role=alert + Retry CTA when isError=true", () => {
    const onRetry = vi.fn()
    const { container } = render(
      <ContactList contacts={[]} selectedId={null} onSelect={() => {}} isError onRetry={onRetry} />,
      { wrapper }
    )

    // role="alert" + aria-live="assertive" on error wrapper
    const alertEl = container.querySelector('[role="alert"][aria-live="assertive"]')
    expect(alertEl).toBeTruthy()

    // Error i18n keys present
    expect(screen.getByText("messenger:error.failedToLoadChats")).toBeTruthy()
    expect(screen.getByText("messenger:error.failedToLoadChatsHint")).toBeTruthy()

    // Retry CTA button present with i18n label
    const retryBtn = screen.getByRole("button", { name: /messenger:error.retry/ })
    expect(retryBtn).toBeTruthy()
  })

  it("Retry CTA fires onRetry callback on click (SW3)", () => {
    const onRetry = vi.fn()
    render(
      <ContactList contacts={[]} selectedId={null} onSelect={() => {}} isError onRetry={onRetry} />,
      { wrapper }
    )

    const retryBtn = screen.getByRole("button", { name: /messenger:error.retry/ })
    fireEvent.click(retryBtn)
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it("branch order: isLoading takes priority over isError + empty contacts", () => {
    // When BOTH isLoading=true AND isError=true, the isLoading branch fires first
    // (code order at ContactList.tsx:117 vs :155). This matches ChatWindow's
    // priority (W184 SW2 test "isError takes priority over isLoading" — different
    // priority because ChatWindow checks isError FIRST, ContactList checks
    // isLoading FIRST). Document the actual order via empirical test.
    const { container } = render(
      <ContactList
        contacts={[]}
        selectedId={null}
        onSelect={() => {}}
        isLoading
        isError
        onRetry={() => {}}
      />,
      { wrapper }
    )

    // Skeleton branch fires (isLoading checked FIRST in ContactList)
    expect(container.querySelector('[role="status"][aria-live="polite"]')).toBeTruthy()
    expect(container.querySelectorAll(".messenger-skeleton.size-12").length).toBe(6)

    // Error branch does NOT fire
    expect(container.querySelector('[role="alert"]')).toBeFalsy()
    expect(screen.queryByText("messenger:error.failedToLoadChats")).toBeFalsy()
  })

  it("renders the reduced-motion error branch without a retry callback", () => {
    mockReducedMotion.mockReturnValue(true)
    const { container } = render(
      <ContactList contacts={[]} selectedId={null} onSelect={() => {}} isError />,
      { wrapper }
    )

    expect(container.querySelector('[role="alert"]')).toBeTruthy()
    expect(screen.queryByRole("button")).toBeFalsy()
  })
})

describe("ContactList — populated contacts", () => {
  beforeEach(() => {
    mockReducedMotion.mockReturnValue(false)
  })

  it("renders active group rows and handles click and Space activation", () => {
    const onSelect = vi.fn()
    render(
      <ContactList
        contacts={[{ ...mockContacts[1]!, isGroup: true, memberCount: 4, unread: 120 }]}
        selectedId="2"
        onSelect={onSelect}
      />,
      { wrapper }
    )

    const row = document.getElementById("messenger-contact-2")!
    expect(row).toHaveAttribute("aria-current", "true")
    expect(screen.getByLabelText('messenger:aria.unread|{"count":120}')).toHaveTextContent("99+")
    fireEvent.click(row)
    fireEvent.keyDown(row, { key: " " })
    expect(onSelect).toHaveBeenCalledTimes(2)
    expect(screen.queryByAltText("Bob")).toBeFalsy()
  })

  it("renders a theme-stable group avatar with custom sizing", () => {
    const { container } = render(<GroupAvatar className="size-14" iconSize={28} />)

    const avatar = container.firstElementChild
    expect(avatar).toHaveClass("size-14", "rounded-full", "flex", "items-center")
    expect(avatar).toHaveAttribute("aria-hidden", "true")
    expect(avatar).toHaveStyle({ background: "var(--messenger-send-bg)" })
    const icon = avatar?.querySelector("svg")
    expect(icon).toHaveAttribute("width", "28")
    expect(icon).toHaveAttribute("height", "28")
    expect(icon).toHaveClass("text-(--color-white)")
  })

  it("uses the documented compact defaults for a standalone group avatar", () => {
    const { container } = render(<GroupAvatar />)
    const avatar = container.firstElementChild!
    const icon = avatar.querySelector("svg")!
    expect(avatar).toHaveClass("w-12", "h-12")
    expect(icon).toHaveAttribute("width", "22")
    expect(icon).toHaveAttribute("height", "22")
  })

  it("renders DM avatar fallback, presence, unread boundary and active styling", () => {
    render(
      <ContactList
        contacts={[
          { ...mockContacts[0]!, avatar: "alice.jpg", unread: 0, online: true },
          { ...mockContacts[1]!, avatar: "", unread: 99, online: false },
          { ...mockContacts[2]!, avatar: "", unread: 100, online: false },
        ]}
        selectedId="1"
        onSelect={() => {}}
      />,
      { wrapper }
    )

    const alice = document.getElementById("messenger-contact-1")!
    const bob = document.getElementById("messenger-contact-2")!
    expect(alice).toHaveAttribute("aria-current", "true")
    expect(alice).toHaveClass("messenger-active-chip")
    expect(alice.querySelector("img")).toHaveAttribute("src", "alice.jpg")
    expect(alice.querySelector(".messenger-online-indicator")).toBeInTheDocument()
    expect(alice.querySelector('[aria-label*="unread"]')).not.toBeInTheDocument()

    expect(bob.querySelector("img")).toHaveAttribute("src", "/fallbacks/default_avatar.png")
    expect(bob.querySelector(".messenger-online-indicator")).not.toBeInTheDocument()
    expect(screen.getByLabelText('messenger:aria.unread|{"count":99}')).toHaveTextContent("99")
    expect(screen.getByLabelText('messenger:aria.unread|{"count":100}')).toHaveTextContent("99+")
  })

  it("uses the current row as a safe fallback when a keyboard target is missing", () => {
    const contacts = [mockContacts[0]!, mockContacts[1]!]
    render(<ContactList contacts={contacts} selectedId={null} onSelect={() => {}} />, { wrapper })
    const firstRow = document.getElementById("messenger-contact-1")!
    firstRow.focus()

    fireEvent.keyDown(firstRow, { key: "ArrowUp" })
    expect(document.activeElement).toBe(firstRow)
  })

  it("keeps focus on the current row when the target data or DOM node disappears", () => {
    const contacts = [mockContacts[0]!, mockContacts[1]!]
    render(<ContactList contacts={contacts} selectedId={null} onSelect={() => {}} />, { wrapper })
    const firstRow = document.getElementById("messenger-contact-1")!
    firstRow.focus()

    // A concurrent list update can remove the target DOM node before the
    // keyboard event is delivered; the current row is the safe focus fallback.
    document.getElementById("messenger-contact-2")?.remove()
    fireEvent.keyDown(firstRow, { key: "ArrowDown" })
    expect(document.activeElement).toBe(firstRow)

    // The same race can leave a sparse snapshot while the old event handler is
    // still alive. Keep the navigation operation total for that malformed
    // transient input as well.
    ;(contacts as unknown as Array<unknown>)[1] = undefined
    fireEvent.keyDown(firstRow, { key: "ArrowDown" })
    expect(document.activeElement).toBe(firstRow)
  })
})
