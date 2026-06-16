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

import { ScheduleSettingsPanel } from "@/components/schedule/ScheduleSettingsPanel"

const baseProps = {
  open: true,
  onClose: vi.fn(),
  weekdayLabels: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
  currentParity: "odd" as const,
  setCurrentParity: vi.fn(),
}

describe("ScheduleSettingsPanel", () => {
  it("renders nothing when closed", () => {
    render(<ScheduleSettingsPanel {...baseProps} open={false} />)
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("renders the settings dialog with title, parity, and weekday toggles when open", () => {
    render(<ScheduleSettingsPanel {...baseProps} />)
    expect(screen.getByRole("dialog", { name: "schedule:settings.title" })).toBeInTheDocument()
    expect(screen.getByText("schedule:parity.odd")).toBeInTheDocument()
    expect(screen.getByText("schedule:parity.even")).toBeInTheDocument()
    expect(screen.getByText("Monday")).toBeInTheDocument()
  })

  it("fires onClose from the close button", async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<ScheduleSettingsPanel {...baseProps} onClose={onClose} />)
    await user.click(screen.getByRole("button", { name: "common:buttons.close" }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it("fires setCurrentParity when the even parity button is clicked", async () => {
    const user = userEvent.setup()
    const setCurrentParity = vi.fn()
    render(<ScheduleSettingsPanel {...baseProps} setCurrentParity={setCurrentParity} />)
    await user.click(screen.getByText("schedule:parity.even"))
    expect(setCurrentParity).toHaveBeenCalledWith("even")
  })
})
