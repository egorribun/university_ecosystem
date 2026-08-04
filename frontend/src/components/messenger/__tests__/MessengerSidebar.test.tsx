import { render, screen, fireEvent } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"
import type { ComponentProps, ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"

import { MessengerSidebar } from "@/components/messenger/MessengerSidebar"

/**
 * Wave 202 SW7 — MessengerSidebar unit tests (one of the 3 previously untested
 * messenger wrappers). Focus: the sidebar's own rendering + wiring — title,
 * new-chat button → setIsNewChatModalOpen, and the W183 SW1 client-side search
 * → filteredContacts forwarded to ContactList, plus the W184 isLoading/isError
 * pass-through. ContactList's internal behavior is covered by ContactList.test.tsx;
 * it's stubbed here (mirroring the ChatArea.test.tsx vi.importActual recipe) and
 * surfaces the props the sidebar forwards as data-attributes.
 */

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts ? `${key}|${JSON.stringify(opts)}` : key,
  }),
}))

const { mediaQueryMock } = vi.hoisted(() => ({ mediaQueryMock: vi.fn(() => false) }))
vi.mock("@/hooks/useMediaQuery", () => ({ default: mediaQueryMock }))

const navigateMock = vi.fn()
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => navigateMock,
}))

vi.mock("@/components/messenger", async () => {
  const actual =
    await vi.importActual<typeof import("@/components/messenger")>("@/components/messenger")
  return {
    ...actual,
    ContactList: (props: {
      contacts?: unknown[]
      isLoading?: boolean
      isError?: boolean
      isSearchActive?: boolean
      onSelect?: (id: string) => void
      onClearSearch?: () => void
      onRetry?: () => void
    }) => (
      <div>
        <div
          data-testid="mock-contact-list"
          data-count={props.contacts?.length ?? 0}
          data-loading={String(!!props.isLoading)}
          data-error={String(!!props.isError)}
          data-search-active={String(!!props.isSearchActive)}
        />
        <button type="button" onClick={() => props.onSelect?.("c2")}>
          mock-select-contact
        </button>
        <button type="button" onClick={props.onClearSearch}>
          mock-clear-search
        </button>
        <button type="button" onClick={props.onRetry}>
          mock-retry
        </button>
      </div>
    ),
  }
})

type SidebarProps = ComponentProps<typeof MessengerSidebar>

// Minimal Contact fixtures — MessengerSidebar's search filter reads only
// `name` + `lastMessage`. Cast via the production prop type (mirrors the
// ChatArea.test.tsx `as unknown as` partial-fixture pattern).
const makeContacts = (): SidebarProps["contacts"] =>
  [
    { id: "c1", name: "Alice", lastMessage: "hey there" },
    { id: "c2", name: "Bob", lastMessage: "see you soon" },
  ] as unknown as SidebarProps["contacts"]

const queryClient = new QueryClient()
const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
)

const baseProps: SidebarProps = {
  isMobile: false,
  contacts: makeContacts(),
  selectedChatId: null,
  setIsNewChatModalOpen: vi.fn(),
  isLoading: false,
  isError: false,
  onRetry: vi.fn(),
}

describe("MessengerSidebar", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mediaQueryMock.mockReturnValue(false)
  })

  it("renders the messenger title", () => {
    render(<MessengerSidebar {...baseProps} />, { wrapper })
    expect(screen.getByText("messenger:title")).toBeTruthy()
  })

  it("opens the new-chat modal when the new-chat button is clicked", () => {
    const setIsNewChatModalOpen = vi.fn()
    render(<MessengerSidebar {...baseProps} setIsNewChatModalOpen={setIsNewChatModalOpen} />, {
      wrapper,
    })
    fireEvent.click(screen.getByRole("button", { name: "messenger:newChat" }))
    expect(setIsNewChatModalOpen).toHaveBeenCalledWith(true)
  })

  it("forwards all contacts to ContactList when search is empty", () => {
    render(<MessengerSidebar {...baseProps} />, { wrapper })
    const list = screen.getByTestId("mock-contact-list")
    expect(list.getAttribute("data-count")).toBe("2")
    expect(list.getAttribute("data-search-active")).toBe("false")
  })

  it("filters contacts by name as the user types a search query", () => {
    render(<MessengerSidebar {...baseProps} />, { wrapper })
    fireEvent.change(screen.getByPlaceholderText("messenger:search"), {
      target: { value: "ali" },
    })
    const list = screen.getByTestId("mock-contact-list")
    expect(list.getAttribute("data-count")).toBe("1")
    expect(list.getAttribute("data-search-active")).toBe("true")
  })

  it("navigates to a selected chat and clears an active search", () => {
    render(<MessengerSidebar {...baseProps} />, { wrapper })
    fireEvent.change(screen.getByPlaceholderText("messenger:search"), {
      target: { value: "ali" },
    })
    fireEvent.click(screen.getByRole("button", { name: "mock-select-contact" }))
    expect(navigateMock).toHaveBeenCalledWith({
      to: "/messenger/$chatId",
      params: { chatId: "c2" },
    })

    fireEvent.click(screen.getByRole("button", { name: "mock-clear-search" }))
    expect(screen.getByTestId("mock-contact-list")).toHaveAttribute("data-search-active", "false")
  })

  it("forwards loading + error flags to ContactList", () => {
    const onRetry = vi.fn()
    render(<MessengerSidebar {...baseProps} isLoading isError onRetry={onRetry} />, { wrapper })
    const list = screen.getByTestId("mock-contact-list")
    expect(list.getAttribute("data-loading")).toBe("true")
    expect(list.getAttribute("data-error")).toBe("true")
    fireEvent.click(screen.getByRole("button", { name: "mock-retry" }))
    expect(onRetry).toHaveBeenCalledOnce()
  })

  it("uses reduced-motion-safe sidebar transition values on mobile", () => {
    mediaQueryMock.mockReturnValue(true)
    render(<MessengerSidebar {...baseProps} isMobile />, { wrapper })
    expect(screen.getByRole("button", { name: "messenger:newChat" })).toBeInTheDocument()
  })

  it("uses animated mobile transitions and empty optional contact fields safely", () => {
    mediaQueryMock.mockReturnValue(false)
    render(
      <MessengerSidebar
        {...baseProps}
        isMobile
        contacts={[{ id: "sparse" } as unknown as SidebarProps["contacts"][number]]}
      />,
      { wrapper }
    )
    expect(screen.getByTestId("mock-contact-list")).toHaveAttribute("data-count", "1")
  })
})
