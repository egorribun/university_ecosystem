import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
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
vi.mock("@/pages/settings/sections", () => ({
  NotificationsSection: ({ dndStart, dndEnd }: { dndStart: string; dndEnd: string }) => (
    <section aria-label="notifications-panel">{`${dndStart}-${dndEnd}`}</section>
  ),
}))

import { SettingsNotifications } from "@/pages/settings/SettingsNotifications"

describe("SettingsNotifications", () => {
  it("renders the dedicated notification settings panel", () => {
    render(<SettingsNotifications setSnackbar={vi.fn()} />)
    expect(screen.getByRole("region", { name: "notifications-panel" })).toHaveTextContent(
      "22:00-07:00"
    )
  })
})
