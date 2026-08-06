import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

vi.mock("@/hooks/useMediaQuery", () => ({ default: () => false }))
vi.mock("@/hooks/useFocusTrap", () => ({ default: () => null }))
vi.mock("@/components/schedule/ExportDropdown", () => ({
  ExportDropdown: () => <div data-testid="export-dropdown" />,
}))

const storeState = {
  weekOffset: 1,
  hiddenWeekdays: [1],
  showPastLessons: false,
  compactMode: true,
}
const actions = {
  toggleWeekday: vi.fn(),
  togglePastLessons: vi.fn(),
  toggleCompactMode: vi.fn(),
  nextWeek: vi.fn(),
  previousWeek: vi.fn(),
  goToCurrentWeek: vi.fn(),
}

vi.mock("@/stores/scheduleUIStore", () => ({
  useWeekOffset: () => storeState.weekOffset,
  useHiddenWeekdays: () => storeState.hiddenWeekdays,
  useScheduleDisplayPreferences: () => ({
    showPastLessons: storeState.showPastLessons,
    compactMode: storeState.compactMode,
  }),
  useScheduleUIActions: () => actions,
}))

import { ScheduleSettingsPanel } from "../ScheduleSettingsPanel"

describe("ScheduleSettingsPanel closure paths", () => {
  it("covers navigation, parity, hidden days, toggles, and both week-offset signs", async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    const setCurrentParity = vi.fn()
    const { container, rerender } = render(
      <ScheduleSettingsPanel
        open
        onClose={onClose}
        weekdayLabels={["Monday", "Tuesday", "Wednesday"]}
        currentParity="even"
        setCurrentParity={setCurrentParity}
      />
    )

    expect(screen.getByText("schedule:toolbar.weekOffset")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "schedule:toolbar.goToToday" })).toBeInTheDocument()
    expect(screen.getByRole("checkbox", { name: "schedule:settings.compactMode" })).toBeChecked()
    expect(screen.getByRole("checkbox", { name: "schedule:settings.showPast" })).not.toBeChecked()

    await user.click(screen.getByRole("button", { name: "schedule:toolbar.prevWeek" }))
    await user.click(screen.getByRole("button", { name: "schedule:toolbar.nextWeek" }))
    await user.click(screen.getByRole("button", { name: "schedule:toolbar.goToToday" }))
    await user.click(screen.getByRole("button", { name: "schedule:parity.odd" }))
    await user.click(screen.getByRole("button", { name: "schedule:parity.even" }))
    await user.click(screen.getByRole("button", { name: "Monday" }))
    await user.click(screen.getByRole("button", { name: "Tuesday" }))
    await user.click(screen.getByRole("checkbox", { name: "schedule:settings.compactMode" }))
    await user.click(screen.getByRole("checkbox", { name: "schedule:settings.showPast" }))
    fireEvent.click(container.querySelector("div.absolute.inset-0")!)

    expect(actions.previousWeek).toHaveBeenCalledOnce()
    expect(actions.nextWeek).toHaveBeenCalledOnce()
    expect(actions.goToCurrentWeek).toHaveBeenCalledOnce()
    expect(actions.toggleWeekday).toHaveBeenNthCalledWith(1, 0)
    expect(actions.toggleWeekday).toHaveBeenNthCalledWith(2, 1)
    expect(actions.toggleCompactMode).toHaveBeenCalledOnce()
    expect(actions.togglePastLessons).toHaveBeenCalledOnce()
    expect(setCurrentParity).toHaveBeenCalledWith("odd")
    expect(setCurrentParity).toHaveBeenCalledWith("even")
    expect(onClose).toHaveBeenCalledOnce()

    storeState.weekOffset = -1
    rerender(
      <ScheduleSettingsPanel
        open
        onClose={onClose}
        weekdayLabels={["Monday", "Tuesday", "Wednesday"]}
        currentParity="odd"
        setCurrentParity={setCurrentParity}
      />
    )
    expect(screen.getByText("schedule:toolbar.weekOffset")).toBeInTheDocument()
  })
})
