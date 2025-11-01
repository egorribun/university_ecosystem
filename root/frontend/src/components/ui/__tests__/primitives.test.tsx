import { useEffect, useState } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  IconButton,
  Modal,
  ModalBody,
  ModalCloseButton,
  ModalContent,
  ModalDescription,
  ModalFooter,
  ModalHeader,
  ModalTitle,
  TextArea,
  TextInput,
  Toast,
  ToastViewport,
} from "@/components/ui"

describe("UI primitives", () => {
  it("renders modal content with accessible attributes and closes on overlay interaction", async () => {
    const user = userEvent.setup()

    function ModalHarness() {
      const [open, setOpen] = useState(true)
      return (
        <>
          <button type="button">Trigger</button>
          <Modal open={open} onOpenChange={setOpen}>
            <ModalContent>
              <ModalHeader>
                <ModalTitle>Schedule update</ModalTitle>
                <ModalDescription>Important information</ModalDescription>
              </ModalHeader>
              <ModalBody>
                <p>Modal body copy</p>
              </ModalBody>
              <ModalFooter>
                <ModalCloseButton>Close</ModalCloseButton>
              </ModalFooter>
            </ModalContent>
          </Modal>
        </>
      )
    }

    render(<ModalHarness />)

    const dialog = await screen.findByRole("dialog", { name: /schedule update/i })
    expect(dialog).toHaveAttribute("aria-modal", "true")
    await waitFor(() => expect(dialog).toHaveFocus())

    const overlay = screen.getByTestId("modal-overlay")
    await user.click(overlay)
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
  })

  it("supports keyboard dismissal via Escape", async () => {
    const user = userEvent.setup()

    function ModalHarness() {
      const [open, setOpen] = useState(true)
      return (
        <>
          <button type="button">Trigger</button>
          <Modal open={open} onOpenChange={setOpen}>
            <ModalContent>
              <ModalHeader>
                <ModalTitle>Keyboard close</ModalTitle>
              </ModalHeader>
              <ModalBody />
              <ModalFooter>
                <ModalCloseButton>Dismiss</ModalCloseButton>
              </ModalFooter>
            </ModalContent>
          </Modal>
        </>
      )
    }

    render(<ModalHarness />)

    const dialog = await screen.findByRole("dialog", { name: /keyboard close/i })
    expect(dialog).toBeInTheDocument()
    await user.keyboard("{Escape}")
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
  })

  it("positions dropdown menu in a portal and supports arrow navigation", async () => {
    const user = userEvent.setup()

    function DropdownHarness() {
      const [open, setOpen] = useState(false)
      useEffect(() => {
        setOpen(true)
      }, [])
      return (
        <DropdownMenu open={open} onOpenChange={setOpen}>
          <DropdownMenuTrigger>Options</DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuItem>First</DropdownMenuItem>
            <DropdownMenuItem disabled>Disabled</DropdownMenuItem>
            <DropdownMenuItem>Second</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )
    }

    render(<DropdownHarness />)

    const menu = await screen.findByRole("menu")
    const portal = document.getElementById("ue-dropdown-root")
    expect(portal).toBeTruthy()
    expect(portal).toContainElement(menu)

    const firstItem = await screen.findByRole("menuitem", { name: "First" })
    await waitFor(() => expect(firstItem).toHaveFocus())

    await user.keyboard("{ArrowDown}")
    const secondItem = await screen.findByRole("menuitem", { name: "Second" })
    expect(secondItem).toHaveFocus()

    await user.keyboard("{Escape}")
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument())
    expect(screen.getByRole("button", { name: /options/i })).toHaveFocus()
  })

  it("passes validation state to text inputs", () => {
    render(
      <div>
        <TextInput label="Headline" required errorText="Required" />
        <TextArea label="Body" successText="Looks good" />
      </div>
    )

    const input = screen.getByLabelText(/Headline/i)
    expect(input).toHaveAttribute("aria-invalid", "true")
    const error = screen.getByText("Required")
    expect(input).toHaveAttribute("aria-describedby", error.id)

    const textarea = screen.getByLabelText(/Body/i)
    expect(textarea).not.toHaveAttribute("aria-invalid")
    expect(screen.getByText("Looks good")).toBeInTheDocument()
  })

  it("renders icon button spinner when loading", () => {
    render(
      <IconButton aria-label="loading" loading>
        <span data-testid="icon">◎</span>
      </IconButton>
    )

    expect(screen.queryByTestId("icon")).not.toBeVisible()
  })

  it("auto dismisses toast after the configured duration", async () => {
    const changeSpy = vi.fn()

    function ToastHarness() {
      const [open, setOpen] = useState(true)
      return (
        <ToastViewport>
          <Toast
            open={open}
            onOpenChange={(next) => {
              changeSpy(next)
              setOpen(next)
            }}
            title="Saved"
            description="Changes stored"
            duration={800}
          />
        </ToastViewport>
      )
    }

    render(<ToastHarness />)

    expect(document.getElementById("ue-toast-root")).toBeTruthy()

    expect(screen.getByRole("status")).toBeInTheDocument()
    await waitFor(() => expect(changeSpy).toHaveBeenCalledWith(false), { timeout: 1500 })
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument())
  })
})

