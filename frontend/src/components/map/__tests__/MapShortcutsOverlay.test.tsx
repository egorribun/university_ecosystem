import { render, screen } from "@testing-library/react"
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
vi.mock("@/hooks/useMediaQuery", () => ({ default: () => true }))

import { MapShortcutsOverlay } from "@/components/map/MapShortcutsOverlay"

const baseProps = { open: true, onClose: vi.fn() }

describe("MapShortcutsOverlay", () => {
  it("renders nothing when closed", () => {
    render(<MapShortcutsOverlay {...baseProps} open={false} />)
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("renders the shortcuts dialog with title and shortcut rows when open", () => {
    render(<MapShortcutsOverlay {...baseProps} />)
    expect(screen.getByRole("dialog", { name: "shortcuts.title" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "shortcuts.title" })).toBeInTheDocument()
    expect(screen.getByText("shortcuts.buildings")).toBeInTheDocument()
    expect(screen.getByText("shortcuts.zoom")).toBeInTheDocument()
    expect(screen.getByText("F")).toBeInTheDocument()
  })

  it("fires onClose from the close button", async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<MapShortcutsOverlay {...baseProps} onClose={onClose} />)
    await user.click(screen.getByRole("button", { name: "sidebar.close" }))
    expect(onClose).toHaveBeenCalledOnce()
  })
})
