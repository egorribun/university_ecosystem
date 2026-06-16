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

import { ExportDropdown } from "@/components/schedule/ExportDropdown"

describe("ExportDropdown", () => {
  it("renders the export trigger button", () => {
    render(<ExportDropdown />)
    expect(screen.getByRole("button", { name: /schedule:toolbar.export/ })).toBeInTheDocument()
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
  })

  it("disables PDF/PNG export when there is no grid ref", async () => {
    const user = userEvent.setup()
    render(<ExportDropdown />)
    await user.click(screen.getByRole("button", { name: /schedule:toolbar.export/ }))
    expect(screen.getByRole("menuitem", { name: "schedule:export.pdf" })).toBeDisabled()
    expect(screen.getByRole("menuitem", { name: "schedule:export.png" })).toBeDisabled()
    expect(screen.getByRole("menuitem", { name: "schedule:export.googleCalendar" })).toBeEnabled()
  })
})
