/**
 * Render coverage tests (testing session 10) for three untested ui primitives:
 * Dialog (portal mount / open-close / Escape / backdrop click / title+subtitle
 * a11y wiring), MediaSlot (no-src fallback / error fallback / loading + image
 * onLoad+onError branches), and the table primitive family. Mirrors the
 * uiPrimitives.test.tsx style (plain render, no router).
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { Dialog } from "@/components/ui/Dialog"
import { MediaSlot } from "@/components/ui/MediaSlot"
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

describe("Dialog", () => {
  it("renders nothing when closed", () => {
    render(
      <Dialog open={false} onClose={vi.fn()} title="Hidden">
        body
      </Dialog>
    )
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("portals an open dialog with title/subtitle a11y wiring", async () => {
    render(
      <Dialog open onClose={vi.fn()} title="My Title" subtitle="My Subtitle">
        <p>dialog body</p>
      </Dialog>
    )
    const dialog = await screen.findByRole("dialog")
    expect(dialog).toHaveAttribute("aria-modal", "true")
    expect(dialog).toHaveAttribute("aria-labelledby")
    expect(dialog).toHaveAttribute("aria-describedby")
    expect(screen.getByText("My Title")).toBeInTheDocument()
    expect(screen.getByText("My Subtitle")).toBeInTheDocument()
    expect(screen.getByText("dialog body")).toBeInTheDocument()
  })

  it("supports an explicit accessible name without a visible title", async () => {
    render(
      <Dialog open onClose={vi.fn()} ariaLabel="Keyboard shortcuts">
        body
      </Dialog>
    )
    expect(await screen.findByRole("dialog", { name: "Keyboard shortcuts" })).toBeInTheDocument()
  })

  it("keeps the close control at least 44px square", async () => {
    render(
      <Dialog open onClose={vi.fn()} title="Close target" closeLabel="Dismiss">
        body
      </Dialog>
    )
    expect(await screen.findByRole("button", { name: "Dismiss" })).toHaveClass("h-11", "w-11")
  })

  it("calls onClose from the close button + backdrop click", async () => {
    const onClose = vi.fn()
    render(
      <Dialog open onClose={onClose} title="Closeable" closeLabel="Dismiss">
        body
      </Dialog>
    )
    await screen.findByRole("dialog")
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }))
    expect(onClose).toHaveBeenCalled()

    // Backdrop (role=presentation's aria-hidden overlay) click also closes.
    const overlay = document.querySelector("[aria-hidden='true'].absolute")
    expect(overlay).not.toBeNull()
    fireEvent.click(overlay as Element)
    expect(onClose.mock.calls.length).toBeGreaterThanOrEqual(2)
  })

  it("renders the footer + fullScreenOnMobile variant", async () => {
    render(
      <Dialog
        open
        onClose={vi.fn()}
        title="WithFooter"
        fullScreenOnMobile
        footer={<button type="button">Confirm</button>}
      >
        body
      </Dialog>
    )
    await screen.findByRole("dialog")
    expect(screen.getByRole("button", { name: "Confirm" })).toBeInTheDocument()
  })

  it("honors a caller-provided initial focus policy", async () => {
    render(
      <Dialog open onClose={vi.fn()} title="Focused" initialFocus={false}>
        <button id="dialog-target" type="button">
          Target
        </button>
      </Dialog>
    )

    const target = await screen.findByRole("button", { name: "Target" })
    expect(target).not.toHaveFocus()
  })
})

describe("MediaSlot", () => {
  it("renders the default icon fallback when no src", () => {
    const { container } = render(<MediaSlot src={undefined} alt="x" />)
    // No <img> rendered in the no-src branch.
    expect(container.querySelector("img")).toBeNull()
    expect(container.querySelector("[style*='aspect-ratio']")).not.toBeNull()
  })

  it("renders a custom fallback node when no src", () => {
    render(<MediaSlot src={undefined} fallback={<span>placeholder</span>} />)
    expect(screen.getByText("placeholder")).toBeInTheDocument()
  })

  it("shows the image, then fires onLoad and clears the loading state", async () => {
    const onLoad = vi.fn()
    render(<MediaSlot src="https://img.example/a.jpg" alt="alt-a" onLoad={onLoad} />)
    const img = screen.getByAltText("alt-a")
    expect(img).toHaveAttribute("loading", "lazy")
    fireEvent.load(img)
    expect(onLoad).toHaveBeenCalledOnce()
  })

  it("swaps to the error fallback + fires onError on image failure", async () => {
    const onError = vi.fn()
    render(
      <MediaSlot
        src="https://img.example/bad.jpg"
        alt="alt-b"
        onError={onError}
        fallback={<span>broken</span>}
      />
    )
    fireEvent.error(screen.getByAltText("alt-b"))
    expect(onError).toHaveBeenCalledOnce()
    await waitFor(() => expect(screen.getByText("broken")).toBeInTheDocument())
  })
})

describe("table primitives", () => {
  it("renders a full semantic table tree", () => {
    render(
      <Table>
        <TableCaption>Caption</TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow data-state="selected">
            <TableCell>Ada</TableCell>
          </TableRow>
        </TableBody>
        <TableFooter>
          <TableRow>
            <TableCell>Total: 1</TableCell>
          </TableRow>
        </TableFooter>
      </Table>
    )
    expect(screen.getByRole("table")).toBeInTheDocument()
    expect(screen.getByText("Caption")).toBeInTheDocument()
    expect(screen.getByRole("columnheader", { name: "Name" })).toBeInTheDocument()
    expect(screen.getByText("Ada")).toBeInTheDocument()
    expect(screen.getByText("Total: 1")).toBeInTheDocument()
  })
})
