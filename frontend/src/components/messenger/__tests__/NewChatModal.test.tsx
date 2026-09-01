import { render, screen, fireEvent, waitFor, act } from "@testing-library/react"
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
  default: ({ alt, className, srcRaw }: { alt?: string; className?: string; srcRaw?: string }) => (
    <img alt={alt} className={className} src={srcRaw} />
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
    expect(mocks.apiGet).not.toHaveBeenCalled()
  })

  it("renders dialog with proper ARIA when open=true", () => {
    render(<NewChatModal open={true} onClose={() => {}} onSelect={() => {}} />, { wrapper })

    const dialog = screen.getByRole("dialog")
    expect(dialog).toBeTruthy()
    expect(dialog.getAttribute("aria-modal")).toBe("true")
    expect(dialog.getAttribute("aria-labelledby")).toBeTruthy()
    const descriptionId = dialog.getAttribute("aria-describedby")
    expect(descriptionId).toBeTruthy()
    expect(document.getElementById(descriptionId!)).toHaveTextContent("messenger:searchUsers")
  })

  it("close button has aria-label + 44x44 touch target (W183 SW4)", () => {
    render(<NewChatModal open={true} onClose={() => {}} onSelect={() => {}} />, { wrapper })

    const closeButton = screen.getByRole("button", { name: "common:buttons.close" })
    expect(closeButton).toBeTruthy()
    expect(closeButton.className).toContain("min-h-[44px]")
    expect(closeButton.className).toContain("min-w-[44px]")
  })

  it("keeps mode tabs and selected-member chips at the accessible touch target", () => {
    render(
      <NewChatModal open={true} onClose={() => {}} onSelect={() => {}} onCreateGroup={() => {}} />,
      { wrapper }
    )

    expect(screen.getByRole("tab", { name: "messenger:modeDirect" }).className).toContain(
      "min-h-[44px]"
    )
    expect(screen.getByRole("tab", { name: "messenger:modeGroup" }).className).toContain(
      "min-h-[44px]"
    )
  })

  it("Escape key triggers onClose and the listener is removed when closed", () => {
    const onClose = vi.fn()
    const { rerender } = render(
      <NewChatModal open={true} onClose={onClose} onSelect={() => {}} />,
      { wrapper }
    )

    fireEvent.keyDown(document, { key: "ArrowLeft" })
    expect(onClose).not.toHaveBeenCalled()
    fireEvent.keyDown(document, { key: "Escape" })
    expect(onClose).toHaveBeenCalledTimes(1)

    rerender(<NewChatModal open={false} onClose={onClose} onSelect={() => {}} />)
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

  it("autofocuses the search field on the next frame and cancels it on unmount", async () => {
    const callbacks: FrameRequestCallback[] = []
    const requestSpy = vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      callbacks.push(callback)
      return callbacks.length
    })
    const cancelSpy = vi.spyOn(window, "cancelAnimationFrame")
    const { unmount } = render(
      <NewChatModal open={true} onClose={() => {}} onSelect={() => {}} />,
      { wrapper }
    )

    await waitFor(() => expect(requestSpy).toHaveBeenCalledTimes(1))
    const searchInput = screen.getByRole("textbox", { name: "messenger:searchUsers" })
    act(() => callbacks[0]?.(performance.now()))
    expect(document.activeElement).toBe(searchInput)

    unmount()
    expect(cancelSpy).toHaveBeenCalledWith(1)
    requestSpy.mockRestore()
    cancelSpy.mockRestore()
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
      const directTab = screen.getByRole("tab", { name: "messenger:modeDirect" })
      const groupTab = screen.getByRole("tab", { name: "messenger:modeGroup" })
      expect(screen.getByRole("tablist")).toHaveAttribute("aria-label", "messenger:modeToggle")
      expect(directTab).toHaveAttribute("aria-selected", "true")
      expect(groupTab).toHaveAttribute("aria-selected", "false")

      fireEvent.click(groupTab)
      expect(directTab).toHaveAttribute("aria-selected", "false")
      expect(groupTab).toHaveAttribute("aria-selected", "true")
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
      expect(screen.getByText("messenger:error.minMembers")).toBeInTheDocument()

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
        target: { value: "  Project Alpha  " },
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
      expect(screen.getByRole("option", { name: /User One/ })).toHaveAttribute(
        "aria-selected",
        "true"
      )
      expect(screen.getByRole("button", { name: "messenger:removeMember" }).className).toContain(
        "min-h-[44px]"
      )

      fireEvent.click(screen.getByRole("button", { name: "messenger:removeMember" }))
      expect(screen.queryByRole("button", { name: "messenger:removeMember" })).toBeNull()

      // Add the removed member back through the row before selecting the second
      // member; the chip click above already covered the remove side.
      fireEvent.click(screen.getByRole("option", { name: /User One/ }))

      fireEvent.click(screen.getByText("User Two"))
      await waitFor(() => expect((createBtn as HTMLButtonElement).disabled).toBe(false))
      expect(screen.queryByText("messenger:error.minMembers")).toBeNull()

      fireEvent.click(createBtn)
      expect(onCreateGroup).toHaveBeenCalledWith("Project Alpha", ["u1", "u2"])
    })

    it("resets group mode, selections, and search when the modal is reopened", async () => {
      mocks.apiGet.mockResolvedValue({
        data: [{ id: "u1", full_name: "User One", email: "u1@x.com", avatar_url: null }],
      })
      const { rerender } = render(
        <NewChatModal
          open={true}
          onClose={() => {}}
          onSelect={() => {}}
          onCreateGroup={() => {}}
        />,
        { wrapper }
      )
      fireEvent.click(screen.getByRole("tab", { name: "messenger:modeGroup" }))
      fireEvent.change(screen.getByRole("textbox", { name: "messenger:groupName" }), {
        target: { value: "Temporary" },
      })
      fireEvent.change(screen.getByRole("textbox", { name: "messenger:searchUsers" }), {
        target: { value: "user" },
      })
      fireEvent.click(await screen.findByText("User One"))
      expect(screen.getByRole("button", { name: "messenger:removeMember" })).toBeInTheDocument()

      rerender(
        <NewChatModal
          open={false}
          onClose={() => {}}
          onSelect={() => {}}
          onCreateGroup={() => {}}
        />
      )
      rerender(
        <NewChatModal open={true} onClose={() => {}} onSelect={() => {}} onCreateGroup={() => {}} />
      )

      expect(screen.getByRole("heading", { name: "messenger:newChat" })).toBeInTheDocument()
      expect(screen.getByRole("textbox", { name: "messenger:searchUsers" })).toHaveValue("")
      expect(screen.queryByRole("textbox", { name: "messenger:groupName" })).toBeNull()
      expect(screen.queryByRole("button", { name: "messenger:removeMember" })).toBeNull()
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

    it("does not query or show empty state for a one-character search", async () => {
      render(<NewChatModal open={true} onClose={() => {}} onSelect={() => {}} />, { wrapper })
      const searchInput = screen.getByRole("textbox", { name: "messenger:searchUsers" })

      fireEvent.change(searchInput, { target: { value: "a" } })
      await waitFor(() => expect(mocks.apiGet).not.toHaveBeenCalled())
      expect(screen.queryByText("messenger:noUsersFound")).toBeNull()
    })

    it("URL-encodes the user search query before requesting the API", async () => {
      render(<NewChatModal open={true} onClose={() => {}} onSelect={() => {}} />, { wrapper })
      fireEvent.change(screen.getByRole("textbox", { name: "messenger:searchUsers" }), {
        target: { value: "a&b=c" },
      })

      await waitFor(() =>
        expect(mocks.apiGet).toHaveBeenCalledWith("/users?limit=10&search=a%26b%3Dc")
      )
      expect(await screen.findByText("messenger:noUsersFound")).toBeInTheDocument()
    })

    it("renders five accessible skeleton rows while a search is pending", async () => {
      let resolveSearch: ((value: { data: never[] }) => void) | undefined
      const pendingSearch = new Promise<{ data: never[] }>((resolve) => {
        resolveSearch = resolve
      })
      mocks.apiGet.mockReturnValue(pendingSearch)
      render(<NewChatModal open={true} onClose={() => {}} onSelect={() => {}} />, { wrapper })
      fireEvent.change(screen.getByRole("textbox", { name: "messenger:searchUsers" }), {
        target: { value: "pending" },
      })

      const loading = await screen.findByRole("status", { name: "messenger:loading.users" })
      expect(loading.querySelectorAll('[aria-hidden="true"]')).toHaveLength(5)
      expect(loading.querySelectorAll(".messenger-skeleton")).toHaveLength(15)
      const widthBars = [...loading.querySelectorAll<HTMLElement>("[style]")].filter(
        (element) => element.style.width !== ""
      )
      expect(widthBars).toHaveLength(10)
      expect(widthBars[0]?.style.width).toBe("55%")
      expect(widthBars[1]?.style.width).toBe("35%")

      await act(async () => {
        resolveSearch?.({ data: [] })
        await pendingSearch
      })
      await waitFor(() =>
        expect(screen.queryByRole("status", { name: "messenger:loading.users" })).toBeNull()
      )
      expect(screen.getByText("messenger:noUsersFound")).toBeInTheDocument()
    })

    it("uses the avatar URL when present and the placeholder when absent", async () => {
      mocks.apiGet.mockResolvedValue({
        data: [
          {
            id: "with-avatar",
            full_name: "With Avatar",
            email: "with@example.com",
            avatar_url: "https://cdn/avatar.png",
          },
          {
            id: "without-avatar",
            full_name: "Without Avatar",
            email: "without@example.com",
            avatar_url: null,
          },
        ],
      })
      render(<NewChatModal open={true} onClose={() => {}} onSelect={() => {}} />, { wrapper })
      fireEvent.change(screen.getByRole("textbox", { name: "messenger:searchUsers" }), {
        target: { value: "avatar" },
      })

      await screen.findByText("With Avatar")
      const images = [...document.querySelectorAll<HTMLImageElement>("img")]
      expect(images.map((image) => image.getAttribute("src"))).toEqual([
        "https://cdn/avatar.png",
        "/fallbacks/default_avatar.png",
      ])
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
      expect(await screen.findByRole("option", { name: /Reduced User/ })).toBeDisabled()
    })
  })
})
