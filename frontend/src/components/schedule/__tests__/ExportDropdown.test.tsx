import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, it, expect, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

import { ExportDropdown } from "@/components/schedule/ExportDropdown"

const calendarUrl =
  "https://calendar.google.com/calendar/r/eventedit?action=TEMPLATE" +
  "&text=Algebra&dates=20261027T091500%2F20261027T104500" +
  "&location=B-202&details=Lecture&ctz=Europe%2FIstanbul"

describe("ExportDropdown", () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("renders the export trigger button", () => {
    render(<ExportDropdown />)
    expect(screen.getByRole("button", { name: /schedule:toolbar.export/ })).toHaveClass("min-h-11")
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
  })

  it("opens the menu with PDF/PNG/Google Calendar items", async () => {
    const user = userEvent.setup()
    render(<ExportDropdown />)
    await user.click(screen.getByRole("button", { name: /schedule:toolbar.export/ }))
    expect(screen.getByRole("menu")).toBeInTheDocument()
    expect(screen.getByRole("menuitem", { name: "schedule:export.pdf" })).toBeInTheDocument()
    expect(screen.getByRole("menuitem", { name: "schedule:export.png" })).toBeInTheDocument()
    expect(
      screen.getByRole("menuitem", { name: "schedule:export.googleCalendar" })
    ).toBeInTheDocument()
    for (const item of screen.getAllByRole("menuitem")) {
      expect(item).toHaveClass("min-h-11")
    }
    const googleCalendarItem = screen.getByRole("menuitem", {
      name: "schedule:export.googleCalendar",
    })
    const unavailableReason = screen.getByText("schedule:export.googleCalendarUnavailable")
    expect(googleCalendarItem).toBeDisabled()
    expect(googleCalendarItem).toHaveAttribute("aria-describedby", unavailableReason.id)
    expect(unavailableReason).toHaveClass("sr-only")
  })

  it("opens the provided Google Calendar URL in a new tab", async () => {
    const user = userEvent.setup()
    const openSpy = vi.spyOn(window, "open").mockReturnValue(null)
    render(<ExportDropdown googleCalendarUrl={calendarUrl} />)
    await user.click(screen.getByRole("button", { name: /schedule:toolbar.export/ }))
    await user.click(screen.getByRole("menuitem", { name: "schedule:export.googleCalendar" }))
    expect(openSpy).toHaveBeenCalledWith(calendarUrl, "_blank", "noopener")
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
  })

  it("disables PDF/PNG export when there is no grid ref", async () => {
    const user = userEvent.setup()
    render(<ExportDropdown googleCalendarUrl={calendarUrl} />)
    await user.click(screen.getByRole("button", { name: /schedule:toolbar.export/ }))
    expect(screen.getByRole("menuitem", { name: "schedule:export.pdf" })).toBeDisabled()
    expect(screen.getByRole("menuitem", { name: "schedule:export.png" })).toBeDisabled()
    expect(screen.getByRole("menuitem", { name: "schedule:export.googleCalendar" })).toBeEnabled()
  })
})
