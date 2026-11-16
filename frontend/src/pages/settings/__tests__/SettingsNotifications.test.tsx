import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  auth: { user: { id: "user-1" }, loading: false },
  state: {
    dndEnabled: true,
    dndStart: "22:00",
    dndEnd: "07:00",
    dndSaving: false,
    handleDndToggle: vi.fn(),
    handleDndStartChange: vi.fn(),
    handleDndStartBlur: vi.fn(),
    handleDndEndChange: vi.fn(),
    handleDndEndBlur: vi.fn(),
  },
}))

vi.mock("@/pages/settings/hooks", () => ({ useDndSettings: () => mocks.state }))
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => mocks.auth }))
vi.mock("@/pages/settings/sections", () => ({
  NotificationsSection: ({
    dndStart,
    dndEnd,
    dndSaving,
  }: {
    dndStart: string
    dndEnd: string
    dndSaving: boolean
  }) => (
    <section
      aria-label="notifications-panel"
      data-dnd-disabled={dndSaving}
    >{`${dndStart}-${dndEnd}`}</section>
  ),
}))

import { SettingsNotifications } from "@/pages/settings/SettingsNotifications"

describe("SettingsNotifications", () => {
  beforeEach(() => {
    mocks.auth.user = { id: "user-1" }
    mocks.auth.loading = false
    mocks.state.dndSaving = false
  })

  it("renders the dedicated notification settings panel", () => {
    render(<SettingsNotifications setSnackbar={vi.fn()} />)
    expect(screen.getByRole("region", { name: "notifications-panel" })).toHaveTextContent(
      "22:00-07:00"
    )
  })

  it.each(["ssr-stub", "-1"])("disables quiet hours for %s until identity is confirmed", (id) => {
    mocks.auth.user = { id }
    const { rerender } = render(<SettingsNotifications setSnackbar={vi.fn()} />)
    const panel = screen.getByRole("region", { name: "notifications-panel" })
    expect(panel).toHaveAttribute("data-dnd-disabled", "true")

    mocks.auth.user = { id: "user-1" }
    rerender(<SettingsNotifications setSnackbar={vi.fn()} />)
    expect(panel).toHaveAttribute("data-dnd-disabled", "false")
  })

  it("keeps quiet hours disabled for an ongoing save after identity confirmation", () => {
    mocks.state.dndSaving = true
    render(<SettingsNotifications setSnackbar={vi.fn()} />)
    expect(screen.getByRole("region", { name: "notifications-panel" })).toHaveAttribute(
      "data-dnd-disabled",
      "true"
    )
  })
})
