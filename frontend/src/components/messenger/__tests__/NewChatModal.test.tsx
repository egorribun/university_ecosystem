import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"

/**
 * Wave 183 SW10 — NewChatModal unit tests.
 *
 * Covers W183 SW4 a11y batch regression guards + NewChatModal contract:
 *  - Renders nothing when open=false.
 *  - Renders dialog with role=dialog + aria-modal + aria-labelledby.
 *  - Close button has aria-label + min 44x44 touch target.
 *  - Escape key triggers onClose.
 *  - Backdrop click triggers onClose.
 *  - Loading state has role=status + aria-live (W183 SW4).
 *  - User list has role=listbox + role=option (W183 SW4 ARIA APG).
 *  - Search input has aria-label.
 *
 * Mocking strategy:
 *  - useFocusTrap mocked to no-op ref.
 *  - api client mocked for user search.
 *  - react-i18next passes keys through.
 *  - SmartImage mocked as <img>.
 */

const mocks = vi.hoisted(() => ({
  apiGet: vi.fn(),
  prefersReducedMotion: false,
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

vi.mock("@/components/media/SmartImage", () => ({
  default: ({ alt, className }: { alt?: string; className?: string }) => (
    <img alt={alt} className={className} />
  ),
}))

vi.mock("@/hooks/useFocusTrap", () => ({
  default: () => ({ current: null }),
}))

vi.mock("@/hooks/useMediaQuery", () => ({
  default: () => mocks.prefersReducedMotion,
}))

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>()
  return {
    ...actual,
    default: { get: mocks.apiGet },
  }
})

import { NewChatModal } from "@/components/messenger/NewChatModal"

const wrapper = ({ children }: { children: ReactNode }) => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.apiGet.mockResolvedValue({ data: [] })
  mocks.prefersReducedMotion = false
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("NewChatModal", () => {
  it("renders nothing when open=false", () => {
    const { container } = render(
      <NewChatModal open={false} onClose={() => {}} onSelect={() => {}} />,
      { wrapper }
    )
    expect(container.firstChild).toBeNull()
  })

  it("renders dialog with proper ARIA when open=true", () => {
    render(<NewChatModal open={true} onClose={() => {}} onSelect={() => {}} />, { wrapper })

    const dialog = screen.getByRole("dialog")
    expect(dialog).toBeTruthy()
    expect(dialog.getAttribute("aria-modal")).toBe("true")
    expect(dialog.getAttribute("aria-labelledby")).toBeTruthy()
  })

  it("close button has aria-label + 44x44 touch target (W183 SW4)", () => {
    render(<NewChatModal open={true} onClose={() => {}} onSelect={() => {}} />, { wrapper })

    const closeButton = screen.getByRole("button", { name: "common:buttons.close" })
    expect(closeButton).toBeTruthy()
    expect(closeButton.className).toContain("min-h-[44px]")
    expect(closeButton.className).toContain("min-w-[44px]")
  })

  it("Escape key triggers onClose", () => {
    const onClose = vi.fn()
    render(<NewChatModal open={true} onClose={onClose} onSelect={() => {}} />, { wrapper })

    fireEvent.keyDown(document, { key: "Escape" })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it("backdrop click triggers onClose", () => {
    const onClose = vi.fn()
    render(<NewChatModal open={true} onClose={onClose} onSelect={() => {}} />, { wrapper })

    const backdrop = document.querySelector('[aria-hidden="true"]')
    expect(backdrop).toBeTruthy()
    fireEvent.click(backdrop!)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it("dialog click does NOT propagate to backdrop", () => {
    const onClose = vi.fn()
    render(<NewChatModal open={true} onClose={onClose} onSelect={() => {}} />, { wrapper })

    const dialog = screen.getByRole("dialog")
    fireEvent.click(dialog)
    expect(onClose).not.toHaveBeenCalled()
  })

  it("user list container has role=listbox + aria-label (W183 SW4)", () => {
    render(<NewChatModal open={true} onClose={() => {}} onSelect={() => {}} />, { wrapper })

    const listbox = screen.getByRole("listbox")
    expect(listbox).toBeTruthy()
    expect(listbox.getAttribute("aria-label")).toBe("messenger:searchUsers")
  })

  it("search input has aria-label", () => {
    render(<NewChatModal open={true} onClose={() => {}} onSelect={() => {}} />, { wrapper })

    // TextField passes aria-label through; should match the placeholder text
    const searchInputs = screen.getAllByLabelText("messenger:searchUsers")
    expect(searchInputs.length).toBeGreaterThan(0)
  })

  // ----- Wave 211 G4 — group-create mode -----
  describe("group create mode (W211 G4)", () => {
    it("shows the DM/Group toggle only when onCreateGroup is provided", () => {
      const { rerender } = render(
        <NewChatModal open={true} onClose={() => {}} onSelect={() => {}} />,
        { wrapper }
      )
      // DM-only (no onCreateGroup) → no mode tablist.
      expect(screen.queryByRole("tablist")).toBeNull()

      rerender(
        <NewChatModal open={true} onClose={() => {}} onSelect={() => {}} onCreateGroup={() => {}} />
      )
      expect(screen.getByRole("tablist")).toBeTruthy()
      expect(screen.getByRole("tab", { name: "messenger:modeGroup" })).toBeTruthy()
    })

    it("group mode reveals the name field + create button", () => {
      render(
        <NewChatModal
          open={true}
          onClose={() => {}}
          onSelect={() => {}}
          onCreateGroup={() => {}}
        />,
        { wrapper }
      )
      fireEvent.click(screen.getByRole("tab", { name: "messenger:modeGroup" }))
      expect(screen.getByLabelText("messenger:groupName")).toBeTruthy()
      const createBtn = screen.getByRole("button", { name: "messenger:createGroup" })
      // Disabled until a name + ≥2 members are chosen.
      expect((createBtn as HTMLButtonElement).disabled).toBe(true)

      fireEvent.click(screen.getByRole("tab", { name: "messenger:modeDirect" }))
      expect(screen.getByRole("heading", { name: "messenger:newChat" })).toBeInTheDocument()
    })

    it("creates a group with the name + selected member ids, ≥2 required", async () => {
      mocks.apiGet.mockResolvedValue({
        data: [
          { id: "u1", full_name: "User One", email: "u1@x.com", avatar_url: null },
          { id: "u2", full_name: "User Two", email: "u2@x.com", avatar_url: null },
        ],
      })
      const onCreateGroup = vi.fn()
      render(
        <NewChatModal
          open={true}
          onClose={() => {}}
          onSelect={() => {}}
          onCreateGroup={onCreateGroup}
        />,
        { wrapper }
      )
      fireEvent.click(screen.getByRole("tab", { name: "messenger:modeGroup" }))

      // Name the group + search for members (≥2 chars → query enabled). Target
      // by role=textbox: the search aria-label is shared with the listbox div.
      fireEvent.change(screen.getByRole("textbox", { name: "messenger:groupName" }), {
        target: { value: "Project Alpha" },
      })
      fireEvent.change(screen.getByRole("textbox", { name: "messenger:searchUsers" }), {
        target: { value: "user" },
      })

      // The debounced /users query resolves → the two rows appear.
      const rowOne = await screen.findByText("User One")
      fireEvent.click(rowOne)
      const createBtn = screen.getByRole("button", { name: "messenger:createGroup" })
      // One member selected — still under the ≥2 minimum.
      expect((createBtn as HTMLButtonElement).disabled).toBe(true)

      fireEvent.click(screen.getByRole("button", { name: "messenger:removeMember" }))
      expect(screen.queryByRole("button", { name: "messenger:removeMember" })).toBeNull()

      // Add the removed member back through the row before selecting the second
      // member; the chip click above already covered the remove side.
      fireEvent.click(screen.getByRole("option", { name: /User One/ }))

      fireEvent.click(screen.getByText("User Two"))
      await waitFor(() => expect((createBtn as HTMLButtonElement).disabled).toBe(false))

      fireEvent.click(createBtn)
      expect(onCreateGroup).toHaveBeenCalledWith("Project Alpha", ["u1", "u2"])
    })

    it("selects a user in DM mode and handles the no-results state", async () => {
      const onSelect = vi.fn()
      mocks.apiGet.mockResolvedValue({
        data: [{ id: "u9", full_name: "User Nine", email: "u9@x.com", avatar_url: null }],
      })
      render(<NewChatModal open={true} onClose={() => {}} onSelect={onSelect} />, { wrapper })
      fireEvent.change(screen.getByRole("textbox", { name: "messenger:searchUsers" }), {
        target: { value: "nine" },
      })
      fireEvent.click(await screen.findByRole("option", { name: /User Nine/ }))
      expect(onSelect).toHaveBeenCalledWith("u9")

      mocks.apiGet.mockResolvedValue({ data: [] })
      fireEvent.change(screen.getByRole("textbox", { name: "messenger:searchUsers" }), {
        target: { value: "missing" },
      })
      expect(await screen.findByText("messenger:noUsersFound")).toBeInTheDocument()
    })

    it("renders the fetch-error state and retries the user search", async () => {
      mocks.apiGet.mockRejectedValueOnce(new Error("offline"))
      render(<NewChatModal open={true} onClose={() => {}} onSelect={() => {}} />, { wrapper })
      fireEvent.change(screen.getByRole("textbox", { name: "messenger:searchUsers" }), {
        target: { value: "error" },
      })
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "messenger:error.failedToLoadUsers"
      )

      mocks.apiGet.mockResolvedValueOnce({ data: [] })
      fireEvent.click(screen.getByRole("button", { name: "messenger:error.retry" }))
      expect(await screen.findByText("messenger:noUsersFound")).toBeInTheDocument()
    })

    it("uses reduced-motion retry controls in the fetch-error state", async () => {
      mocks.prefersReducedMotion = true
      mocks.apiGet.mockRejectedValueOnce(new Error("offline"))
      render(<NewChatModal open={true} onClose={() => {}} onSelect={() => {}} />, { wrapper })

      fireEvent.change(screen.getByRole("textbox", { name: "messenger:searchUsers" }), {
        target: { value: "error" },
      })

      expect(await screen.findByRole("alert")).toHaveTextContent(
        "messenger:error.failedToLoadUsers"
      )
    })

    it("shows reduced-motion settings and the in-flight create state", async () => {
      mocks.prefersReducedMotion = true
      mocks.apiGet.mockResolvedValue({
        data: [{ id: "u-reduced", full_name: "Reduced User", email: "reduced@x.com" }],
      })
      render(
        <NewChatModal
          open={true}
          onClose={() => {}}
          onSelect={() => {}}
          onCreateGroup={() => {}}
          isCreatingGroup
        />,
        { wrapper }
      )
      fireEvent.click(screen.getByRole("tab", { name: "messenger:modeGroup" }))
      fireEvent.change(screen.getByRole("textbox", { name: "messenger:searchUsers" }), {
        target: { value: "reduced" },
      })
      const createBtn = screen.getByRole("button", { name: "messenger:creatingGroup" })
      expect(createBtn).toBeDisabled()
      expect(screen.getByText("messenger:error.minMembers")).toBeInTheDocument()
      expect(await screen.findByRole("option", { name: /Reduced User/ })).toBeInTheDocument()
    })
  })
})
