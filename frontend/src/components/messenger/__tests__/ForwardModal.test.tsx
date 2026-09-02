import { render, screen, fireEvent } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"
import { ForwardModal } from "../ForwardModal"
import type { Contact } from "../types"

const mediaQueryState = vi.hoisted(() => ({ reduced: false }))
const focusTrapMock = vi.hoisted(() => vi.fn(() => ({ current: null })))

vi.mock("@/hooks/useMediaQuery", () => ({
  default: () => mediaQueryState.reduced,
}))

/**
 * Wave 211 — ForwardModal unit tests.
 *
 * Covers:
 *  - Renders nothing when open=false.
 *  - Renders dialog with role=dialog + aria-modal + aria-labelledby.
 *  - Lists contacts, displaying names/avatars.
 *  - Marks the current chat with "(current)".
 *  - Shows empty state if contacts list is empty.
 *  - Triggers onSelect callback on click.
 *  - Triggers onClose callback on Close button click, Escape key, or backdrop click.
 *  - Handles isForwarding loading state (disables interactions).
 */

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts ? `${key}|${JSON.stringify(opts)}` : key,
  }),
}))

vi.mock("@/components/media/SmartImage", () => ({
  default: ({ srcRaw, alt, className }: { srcRaw?: string; alt?: string; className?: string }) => (
    <img src={srcRaw} alt={alt} className={className} data-testid="smart-image" />
  ),
}))

vi.mock("@/hooks/useFocusTrap", () => ({
  default: focusTrapMock,
}))

const mockContacts: Contact[] = [
  {
    id: "contact-1",
    name: "John Doe",
    avatar: "john.png",
    lastMessage: "Hey there!",
    lastMessageTime: "12:34 PM",
    unread: 0,
    online: true,
  },
  {
    id: "contact-2",
    name: "Jane Smith",
    avatar: "jane.png",
    lastMessage: "See you later",
    lastMessageTime: "1:00 PM",
    unread: 2,
    online: false,
  },
]

describe("ForwardModal", () => {
  beforeEach(() => {
    focusTrapMock.mockClear()
    mediaQueryState.reduced = false
  })

  it("renders nothing when open=false", () => {
    const { container } = render(
      <ForwardModal open={false} onClose={() => {}} contacts={mockContacts} onSelect={() => {}} />
    )
    expect(container.firstChild).toBeNull()
  })

  it("renders dialog with proper ARIA when open=true", () => {
    render(
      <ForwardModal open={true} onClose={() => {}} contacts={mockContacts} onSelect={() => {}} />
    )

    const dialog = screen.getByRole("dialog")
    expect(dialog).toBeTruthy()
    expect(dialog.getAttribute("aria-modal")).toBe("true")
    expect(dialog.getAttribute("aria-labelledby")).toBeTruthy()
    expect(screen.getByRole("heading", { name: "messenger:forwardTo" })).toBeTruthy()
    expect(focusTrapMock).toHaveBeenCalledWith(
      expect.objectContaining({
        active: true,
        initialFocus: false,
        returnFocus: true,
        onDeactivate: expect.any(Function),
      })
    )
  })

  it("configures an inactive focus trap while the modal is closed", () => {
    render(
      <ForwardModal open={false} onClose={() => {}} contacts={mockContacts} onSelect={() => {}} />
    )
    expect(focusTrapMock).toHaveBeenCalledWith(
      expect.objectContaining({ active: false, initialFocus: false, returnFocus: true })
    )
  })

  it("close button has aria-label + 44x44 touch target", () => {
    render(
      <ForwardModal open={true} onClose={() => {}} contacts={mockContacts} onSelect={() => {}} />
    )

    const closeButton = screen.getByRole("button", { name: "common:buttons.close" })
    expect(closeButton).toBeTruthy()
    expect(closeButton.className).toContain("min-h-[44px]")
    expect(closeButton.className).toContain("min-w-[44px]")
  })

  it("lists contacts, displaying names, avatars and last messages", () => {
    render(
      <ForwardModal open={true} onClose={() => {}} contacts={mockContacts} onSelect={() => {}} />
    )

    expect(screen.getByText("John Doe")).toBeTruthy()
    expect(screen.getByText("Jane Smith")).toBeTruthy()
    expect(screen.getByText("Hey there!")).toBeTruthy()
    expect(screen.getByText("See you later")).toBeTruthy()

    const images = screen.getAllByTestId("smart-image")
    expect(images).toHaveLength(2)
    expect(images[0]?.getAttribute("src")).toBe("john.png")
    expect(images[1]?.getAttribute("src")).toBe("jane.png")
  })

  it("marks the current chat with (current)", () => {
    render(
      <ForwardModal
        open={true}
        onClose={() => {}}
        contacts={mockContacts}
        currentChatId="contact-1"
        onSelect={() => {}}
      />
    )

    expect(screen.getByText("messenger:forwardCurrentChat")).toBeTruthy()
  })

  it("uses the avatar fallback and omits current/empty-message decorations when absent", () => {
    render(
      <ForwardModal
        open={true}
        onClose={() => {}}
        contacts={[{ ...mockContacts[0]!, id: "fallback", avatar: "", lastMessage: "" }]}
        onSelect={() => {}}
      />
    )

    expect(screen.getByTestId("smart-image")).toHaveAttribute(
      "src",
      "/fallbacks/default_avatar.png"
    )
    expect(screen.queryByText("messenger:forwardCurrentChat")).not.toBeInTheDocument()
    expect(screen.queryByText("Hey there!")).not.toBeInTheDocument()
  })

  it("shows empty state when contacts list is empty", () => {
    render(<ForwardModal open={true} onClose={() => {}} contacts={[]} onSelect={() => {}} />)

    expect(screen.getByRole("status")).toBeTruthy()
    expect(screen.getByText("messenger:forwardNoChats")).toBeTruthy()
  })

  it("triggers onSelect callback when a contact is selected", () => {
    const onSelect = vi.fn()
    render(
      <ForwardModal open={true} onClose={() => {}} contacts={mockContacts} onSelect={onSelect} />
    )

    const button = screen.getByRole("option", { name: /John Doe/ })
    fireEvent.click(button)
    expect(onSelect).toHaveBeenCalledTimes(1)
    expect(onSelect).toHaveBeenCalledWith("contact-1")
  })

  it("Escape key triggers onClose", () => {
    const onClose = vi.fn()
    render(
      <ForwardModal open={true} onClose={onClose} contacts={mockContacts} onSelect={() => {}} />
    )

    fireEvent.keyDown(document, { key: "ArrowLeft" })
    expect(onClose).not.toHaveBeenCalled()
    fireEvent.keyDown(document, { key: "Escape" })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it("removes the Escape listener when closed or unmounted", () => {
    const add = vi.spyOn(document, "addEventListener")
    const remove = vi.spyOn(document, "removeEventListener")
    const onClose = vi.fn()
    const view = render(
      <ForwardModal open={true} onClose={onClose} contacts={mockContacts} onSelect={() => {}} />
    )
    const registration = add.mock.calls.find(([type]) => type === "keydown")
    expect(registration).toBeDefined()
    const handler = registration![1]
    view.rerender(
      <ForwardModal open={false} onClose={onClose} contacts={mockContacts} onSelect={() => {}} />
    )
    expect(remove).toHaveBeenCalledWith("keydown", handler)
  })

  it("backdrop click triggers onClose", () => {
    const onClose = vi.fn()
    render(
      <ForwardModal open={true} onClose={onClose} contacts={mockContacts} onSelect={() => {}} />
    )

    const backdrop = document.querySelector('[aria-hidden="true"]')
    expect(backdrop).toBeTruthy()
    fireEvent.click(backdrop!)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it("dialog click does NOT propagate to backdrop", () => {
    const onClose = vi.fn()
    render(
      <ForwardModal open={true} onClose={onClose} contacts={mockContacts} onSelect={() => {}} />
    )

    const dialog = screen.getByRole("dialog")
    fireEvent.click(dialog)
    expect(onClose).not.toHaveBeenCalled()
  })

  it("disables listbox and items during isForwarding", () => {
    const onSelect = vi.fn()
    render(
      <ForwardModal
        open={true}
        onClose={() => {}}
        contacts={mockContacts}
        onSelect={onSelect}
        isForwarding={true}
      />
    )

    const listbox = screen.getByRole("listbox")
    expect(listbox.getAttribute("aria-busy")).toBe("true")

    const options = screen.getAllByRole("option")
    expect(options).toHaveLength(2)

    options.forEach((opt) => {
      expect((opt as HTMLButtonElement).disabled).toBe(true)
    })

    // Try clicking one
    expect(options[0]).toBeTruthy()
    fireEvent.click(options[0]!)
    expect(onSelect).not.toHaveBeenCalled()
  })

  it("uses avatar and message fallbacks and reduced-motion dialog transitions", () => {
    mediaQueryState.reduced = true
    render(
      <ForwardModal
        open={true}
        onClose={() => {}}
        contacts={[{ ...mockContacts[0]!, id: "fallback", avatar: "", lastMessage: "" }]}
        onSelect={() => {}}
      />
    )

    expect(screen.getByTestId("smart-image")).toHaveAttribute(
      "src",
      "/fallbacks/default_avatar.png"
    )
    expect(screen.queryByText("Hey there!")).not.toBeInTheDocument()
    mediaQueryState.reduced = false
  })
})
