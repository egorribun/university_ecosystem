import { createRef } from "react"
import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi, beforeEach } from "vitest"

type ExportResult = { success: boolean; error?: string }
const exportMocks = vi.hoisted(() => ({
  png: vi.fn<() => Promise<ExportResult>>(() => Promise.resolve({ success: true })),
  pdf: vi.fn<() => Promise<ExportResult>>(() => Promise.resolve({ success: true })),
}))

vi.mock("@/utils/scheduleExport", () => ({
  exportScheduleAsPng: exportMocks.png,
  exportScheduleAsPdf: exportMocks.pdf,
}))
vi.mock("@/app/logger", () => ({ logError: vi.fn() }))
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
import { logError } from "@/app/logger"

function gridRefWithEl() {
  const ref = createRef<HTMLElement>()
  // jsdom-attached element so `gridRef.current` is truthy → PDF/PNG enabled.
  const el = document.createElement("div")
  document.body.appendChild(el)
  ;(ref as { current: HTMLElement | null }).current = el
  return ref
}

const trigger = () => screen.getByRole("button", { name: /schedule:toolbar.export/ })

describe("ExportDropdown — branches", () => {
  beforeEach(() => {
    exportMocks.png.mockClear()
    exportMocks.png.mockResolvedValue({ success: true })
    exportMocks.pdf.mockClear()
    exportMocks.pdf.mockResolvedValue({ success: true })
    vi.mocked(logError).mockClear()
  })

  it("exports PNG via the dynamic-import path when a grid ref is present", async () => {
    const user = userEvent.setup()
    render(<ExportDropdown gridRef={gridRefWithEl()} />)
    await user.click(trigger())
    await user.click(screen.getByRole("menuitem", { name: "schedule:export.png" }))

    await waitFor(() => expect(exportMocks.png).toHaveBeenCalledTimes(1))
    // Menu closes in the finally block after a successful export.
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument())
    expect(logError).not.toHaveBeenCalled()
  })

  it("logs when PNG export returns a non-success result", async () => {
    const user = userEvent.setup()
    exportMocks.png.mockResolvedValueOnce({ success: false, error: "boom" })
    render(<ExportDropdown gridRef={gridRefWithEl()} />)
    await user.click(trigger())
    await user.click(screen.getByRole("menuitem", { name: "schedule:export.png" }))

    await waitFor(() => expect(logError).toHaveBeenCalledWith("[schedule:export:png]", "boom"))
  })

  it("logs when PNG export throws", async () => {
    const user = userEvent.setup()
    exportMocks.png.mockRejectedValueOnce(new Error("explode"))
    render(<ExportDropdown gridRef={gridRefWithEl()} />)
    await user.click(trigger())
    await user.click(screen.getByRole("menuitem", { name: "schedule:export.png" }))

    await waitFor(() =>
      expect(logError).toHaveBeenCalledWith("[schedule:export:png]", expect.any(Error))
    )
  })

  it("exports PDF via the dynamic-import path with the schedule title", async () => {
    const user = userEvent.setup()
    render(<ExportDropdown gridRef={gridRefWithEl()} />)
    await user.click(trigger())
    await user.click(screen.getByRole("menuitem", { name: "schedule:export.pdf" }))

    await waitFor(() => expect(exportMocks.pdf).toHaveBeenCalledTimes(1))
    expect(exportMocks.pdf).toHaveBeenCalledWith(expect.any(HTMLElement), "schedule:title.default")
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument())
  })

  it("logs when PDF export returns a non-success result", async () => {
    const user = userEvent.setup()
    exportMocks.pdf.mockResolvedValueOnce({ success: false, error: "pdf-fail" })
    render(<ExportDropdown gridRef={gridRefWithEl()} />)
    await user.click(trigger())
    await user.click(screen.getByRole("menuitem", { name: "schedule:export.pdf" }))

    await waitFor(() => expect(logError).toHaveBeenCalledWith("[schedule:export:pdf]", "pdf-fail"))
  })

  it("logs when PDF export throws", async () => {
    const user = userEvent.setup()
    exportMocks.pdf.mockRejectedValueOnce(new Error("pdf-explode"))
    render(<ExportDropdown gridRef={gridRefWithEl()} />)
    await user.click(trigger())
    await user.click(screen.getByRole("menuitem", { name: "schedule:export.pdf" }))

    await waitFor(() =>
      expect(logError).toHaveBeenCalledWith("[schedule:export:pdf]", expect.any(Error))
    )
  })

  it("opens Google Calendar in a new tab and closes the menu", async () => {
    const user = userEvent.setup()
    const openSpy = vi.spyOn(window, "open").mockReturnValue(null)
    render(<ExportDropdown gridRef={gridRefWithEl()} />)
    await user.click(trigger())
    await user.click(screen.getByRole("menuitem", { name: "schedule:export.googleCalendar" }))

    expect(openSpy).toHaveBeenCalledWith(
      "https://calendar.google.com/calendar/r/week",
      "_blank",
      "noopener"
    )
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument())
    openSpy.mockRestore()
  })

  it("PNG export is a no-op when there is no grid ref (early return)", async () => {
    const user = userEvent.setup()
    render(<ExportDropdown />)
    await user.click(trigger())
    // Disabled menuitems can't be clicked; assert the disabled state covers the
    // `disabled: !gridRef?.current` true-branch.
    expect(screen.getByRole("menuitem", { name: "schedule:export.png" })).toBeDisabled()
    expect(exportMocks.png).not.toHaveBeenCalled()
  })

  it("renders the busy spinner when isExporting is true", () => {
    render(<ExportDropdown isExporting />)
    // The spinner replaces the Download icon; the trigger still shows the label.
    expect(trigger()).toBeInTheDocument()
    expect(trigger().querySelector(".animate-spin")).toBeInTheDocument()
  })

  it("closes the menu on Escape (keydown effect Escape branch)", async () => {
    const user = userEvent.setup()
    render(<ExportDropdown gridRef={gridRefWithEl()} />)
    await user.click(trigger())
    expect(screen.getByRole("menu")).toBeInTheDocument()

    fireEvent.keyDown(document, { key: "Escape" })
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument())
  })

  it("keeps the menu open for a key unrelated to menu navigation", async () => {
    const user = userEvent.setup()
    render(<ExportDropdown gridRef={gridRefWithEl()} />)
    await user.click(trigger())

    fireEvent.keyDown(document, { key: "Tab" })

    expect(screen.getByRole("menu")).toBeInTheDocument()
  })

  it("navigates menu items with ArrowDown / ArrowUp (keydown effect arrow branch)", async () => {
    const user = userEvent.setup()
    render(<ExportDropdown gridRef={gridRefWithEl()} />)
    await user.click(trigger())

    const pdfItem = screen.getByRole("menuitem", { name: "schedule:export.pdf" })
    pdfItem.focus()

    fireEvent.keyDown(document, { key: "ArrowDown" })
    expect(document.activeElement).toBe(
      screen.getByRole("menuitem", { name: "schedule:export.png" })
    )

    fireEvent.keyDown(document, { key: "ArrowUp" })
    expect(document.activeElement).toBe(pdfItem)
  })

  it("closes the menu on outside mousedown (outside-click effect)", async () => {
    const user = userEvent.setup()
    render(
      <div>
        <span data-testid="outside">outside</span>
        <ExportDropdown gridRef={gridRefWithEl()} />
      </div>
    )
    await user.click(trigger())
    expect(screen.getByRole("menu")).toBeInTheDocument()

    fireEvent.mouseDown(screen.getByTestId("outside"))
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument())
  })
})
