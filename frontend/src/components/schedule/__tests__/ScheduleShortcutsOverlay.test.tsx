import { render, screen, fireEvent } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))
const mediaState = vi.hoisted(() => ({ prefersReduced: true }))
vi.mock("@/hooks/useMediaQuery", () => ({ default: () => mediaState.prefersReduced }))

import { ScheduleShortcutsOverlay } from "@/components/schedule/ScheduleShortcutsOverlay"

const baseProps = { open: true, onClose: vi.fn() }

describe("ScheduleShortcutsOverlay", () => {
  it("renders nothing when closed", () => {
    render(<ScheduleShortcutsOverlay {...baseProps} open={false} />)
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("renders the dialog with title and shortcut rows when open", () => {
    render(<ScheduleShortcutsOverlay {...baseProps} />)
    expect(screen.getByRole("dialog", { name: "schedule:shortcuts.title" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "schedule:shortcuts.title" })).toBeInTheDocument()
    expect(screen.getByText("schedule:shortcuts.arrowNav")).toBeInTheDocument()
    expect(screen.getByText("schedule:shortcuts.today")).toBeInTheDocument()
    expect(screen.getByText("Enter")).toBeInTheDocument()
    expect(screen.getByText("Esc")).toBeInTheDocument()
  })

  it("uses the spring transition when reduced motion is disabled", () => {
    mediaState.prefersReduced = false
    try {
      render(<ScheduleShortcutsOverlay {...baseProps} />)
      expect(screen.getByRole("dialog")).toBeInTheDocument()
    } finally {
      mediaState.prefersReduced = true
    }
  })

  it("fires onClose from the close button", async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<ScheduleShortcutsOverlay {...baseProps} onClose={onClose} />)
    await user.click(screen.getByRole("button", { name: "common:buttons.close" }))
    expect(onClose).toHaveBeenCalled()
  })

  it("fires onClose when the backdrop is clicked", () => {
    const onClose = vi.fn()
    const { container } = render(<ScheduleShortcutsOverlay {...baseProps} onClose={onClose} />)
    const backdrop = container.querySelector('div[aria-hidden="true"]')
    expect(backdrop).not.toBeNull()
    fireEvent.click(backdrop!)
    expect(onClose).toHaveBeenCalled()
  })

  it("fires onClose when the focus trap deactivates on Escape", () => {
    const onClose = vi.fn()
    render(<ScheduleShortcutsOverlay {...baseProps} onClose={onClose} />)

    fireEvent.keyDown(document, { key: "Escape" })
    expect(onClose).toHaveBeenCalledOnce()
  })
})
