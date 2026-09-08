import { createRef } from "react"
import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi, beforeEach } from "vitest"

type ExportResult = { success: boolean; error?: string }
const exportMocks = vi.hoisted(() => ({
  png: vi.fn<() => Promise<ExportResult>>(() => Promise.resolve({ success: true })),
  pdf: vi.fn<() => Promise<ExportResult>>(() => Promise.resolve({ success: true })),
}))
const translationMocks = vi.hoisted(() => ({
  useTranslation: vi.fn(() => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  })),
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
  useTranslation: translationMocks.useTranslation,
}))

import {
  ExportDropdown,
  getExportMenuNextIndex,
  getExportChevronClass,
  getExportMenuMotion,
  isExportItemDisabled,
  shouldHandleExportMenuKey,
  shouldListenForExportMenu,
  shouldShowExportSpinner,
} from "@/components/schedule/ExportDropdown"
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
    translationMocks.useTranslation.mockClear()
  })

  it("keeps menu navigation and disabled-state predicates exact", () => {
    expect(getExportMenuNextIndex(0, "next", 3)).toBe(1)
    expect(getExportMenuNextIndex(2, "next", 3)).toBe(0)
    expect(getExportMenuNextIndex(0, "previous", 3)).toBe(2)
    expect(getExportMenuNextIndex(2, "previous", 3)).toBe(1)
    expect(getExportMenuNextIndex(-1, "next", 3)).toBe(0)
    expect(getExportMenuNextIndex(-1, "previous", 3)).toBe(1)
    expect(getExportMenuNextIndex(0, "next", 0)).toBe(-1)

    expect(isExportItemDisabled(false, null, "png")).toBe(true)
    expect(isExportItemDisabled(true, null, "png")).toBe(false)
    expect(isExportItemDisabled(true, "png", "png")).toBe(true)
    expect(isExportItemDisabled(true, "pdf", "png")).toBe(false)
    expect(getExportMenuNextIndex(0, "next", -1)).toBe(-1)
    expect(shouldHandleExportMenuKey("ArrowDown")).toBe(true)
    expect(shouldHandleExportMenuKey("ArrowUp")).toBe(true)
    expect(shouldHandleExportMenuKey("Tab")).toBe(false)
    expect(shouldListenForExportMenu(true)).toBe(true)
    expect(shouldListenForExportMenu(false)).toBe(false)
    expect(shouldShowExportSpinner(undefined, null)).toBe(false)
    expect(shouldShowExportSpinner(false, "png")).toBe(true)
    expect(shouldShowExportSpinner(true, null)).toBe(true)
    expect(getExportChevronClass(false)).toBe(
      "shrink-0 opacity-50 transition-transform duration-200 "
    )
    expect(getExportChevronClass(true)).toBe(
      "shrink-0 opacity-50 transition-transform duration-200 rotate-180"
    )
    expect(getExportMenuMotion()).toEqual({
      initial: { opacity: 0, y: -4, scale: 0.95 },
      animate: { opacity: 1, y: 0, scale: 1 },
      exit: { opacity: 0, y: -4, scale: 0.95 },
      transition: { duration: 0.15 },
    })
  })

  it("passes the schedule namespace to i18next and stays idle without a spinner", () => {
    render(<ExportDropdown />)
    expect(translationMocks.useTranslation).toHaveBeenCalledWith(["schedule"])
    expect(trigger().querySelector(".animate-spin")).not.toBeInTheDocument()
  })

  it("publishes stable export-format identifiers for each menu item", async () => {
    const user = userEvent.setup()
    render(<ExportDropdown gridRef={gridRefWithEl()} />)
    await user.click(trigger())
    const items = screen.getAllByRole("menuitem")
    expect(Array.from(items, (item) => item.getAttribute("data-export-format"))).toEqual([
      "pdf",
      "png",
      "gcal",
    ])
    for (const item of items) {
      expect(item).toHaveClass("min-h-11")
    }
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

  it("uses a replacement grid ref after rerendering", async () => {
    const user = userEvent.setup()
    const firstRef = gridRefWithEl()
    const secondRef = gridRefWithEl()
    const { rerender } = render(<ExportDropdown gridRef={firstRef} />)
    rerender(<ExportDropdown gridRef={secondRef} />)
    await user.click(trigger())
    await user.click(screen.getByRole("menuitem", { name: "schedule:export.png" }))

    await waitFor(() => expect(exportMocks.png).toHaveBeenCalledWith(secondRef.current))
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

  it("keeps the PDF item busy until the PDF promise settles", async () => {
    const user = userEvent.setup()
    let resolveExport!: (result: ExportResult) => void
    exportMocks.pdf.mockImplementationOnce(
      () => new Promise((resolve) => (resolveExport = resolve))
    )
    render(<ExportDropdown gridRef={gridRefWithEl()} />)
    await user.click(trigger())
    await user.click(screen.getByRole("menuitem", { name: "schedule:export.pdf" }))

    const pdfItem = screen.getByRole("menuitem", { name: "schedule:export.pdf" })
    const pngItem = screen.getByRole("menuitem", { name: "schedule:export.png" })
    await waitFor(() => expect(pdfItem).toBeDisabled())
    expect(pdfItem).toHaveAttribute("data-export-format", "pdf")
    expect(pdfItem.querySelector(".animate-spin")).toBeInTheDocument()
    expect(pngItem).toBeEnabled()
    expect(pngItem.querySelector(".animate-spin")).not.toBeInTheDocument()
    expect(pngItem.querySelector("svg")).toBeInTheDocument()
    resolveExport({ success: true })
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

  it("rotates the chevron only while the menu is open and preserves custom classes", async () => {
    const user = userEvent.setup()
    render(<ExportDropdown className="custom-export" gridRef={gridRefWithEl()} />)
    const button = trigger()
    expect(button.parentElement).toHaveClass("custom-export")
    expect(button.parentElement).toHaveClass("relative", "z-30")
    expect(button.querySelector("svg")).not.toHaveClass("rotate-180")
    await user.click(button)
    const icons = screen
      .getByRole("button", { name: /schedule:toolbar.export/ })
      .querySelectorAll("svg")
    expect(icons[icons.length - 1]).toHaveClass("rotate-180")
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

    const event = new KeyboardEvent("keydown", { key: "Tab", cancelable: true })
    document.dispatchEvent(event)

    expect(screen.getByRole("menu")).toBeInTheDocument()
    expect(event.defaultPrevented).toBe(false)
  })

  it("removes outside and keyboard listeners after the menu closes", async () => {
    const addSpy = vi.spyOn(document, "addEventListener")
    const removeSpy = vi.spyOn(document, "removeEventListener")
    const user = userEvent.setup()
    render(<ExportDropdown gridRef={gridRefWithEl()} />)
    await user.click(trigger())
    await user.click(trigger())
    expect(removeSpy).toHaveBeenCalledWith("mousedown", expect.any(Function))
    expect(removeSpy).toHaveBeenCalledWith("keydown", expect.any(Function))
    expect(addSpy).toHaveBeenCalledWith("mousedown", expect.any(Function))
    expect(addSpy).toHaveBeenCalledWith("keydown", expect.any(Function))
    addSpy.mockRestore()
    removeSpy.mockRestore()
  })

  it("applies the complete menu animation contract", async () => {
    const user = userEvent.setup()
    render(<ExportDropdown gridRef={gridRefWithEl()} />)
    await user.click(trigger())
    const menu = screen.getByRole("menu")
    expect(menu).toHaveClass("sched-export-dropdown")
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

    fireEvent.keyDown(document, { key: "ArrowUp" })
    expect(document.activeElement).toBe(
      screen.getByRole("menuitem", { name: "schedule:export.googleCalendar" })
    )

    const gcalItem = screen.getByRole("menuitem", { name: "schedule:export.googleCalendar" })
    gcalItem.focus()
    fireEvent.keyDown(document, { key: "ArrowDown" })
    expect(document.activeElement).toBe(pdfItem)
  })

  it("marks the active export item busy until its promise settles", async () => {
    const user = userEvent.setup()
    let resolveExport!: (result: ExportResult) => void
    exportMocks.png.mockImplementationOnce(
      () => new Promise((resolve) => (resolveExport = resolve))
    )
    render(<ExportDropdown gridRef={gridRefWithEl()} />)
    await user.click(trigger())
    await user.click(screen.getByRole("menuitem", { name: "schedule:export.png" }))

    const pngItem = screen.getByRole("menuitem", { name: "schedule:export.png" })
    const pdfItem = screen.getByRole("menuitem", { name: "schedule:export.pdf" })
    await waitFor(() => expect(pngItem).toBeDisabled())
    expect(pngItem.querySelector(".animate-spin")).toBeInTheDocument()
    expect(pdfItem).toBeEnabled()
    expect(pdfItem.querySelector(".animate-spin")).not.toBeInTheDocument()
    expect(pdfItem.querySelector("svg")).toBeInTheDocument()
    resolveExport({ success: true })
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument())
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
