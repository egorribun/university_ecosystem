import { render, screen, waitFor, act, fireEvent } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"

const { exportMock } = vi.hoisted(() => ({
  exportMock: { pdf: vi.fn(), png: vi.fn() },
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))
vi.mock("@/utils/activityExport", () => ({
  exportActivityAsPdf: (...args: unknown[]) => exportMock.pdf(...args),
  exportActivityAsPng: (...args: unknown[]) => exportMock.png(...args),
}))

import { ActivityExportButton } from "@/features/activity/components/ActivityExportButton"

function renderButton() {
  const contentRef = { current: document.createElement("div") }
  return render(<ActivityExportButton contentRef={contentRef} />)
}

describe("ActivityExportButton", () => {
  beforeEach(() => {
    exportMock.pdf.mockResolvedValue({ success: true })
    exportMock.png.mockResolvedValue({ success: true })
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it("renders the trigger collapsed", () => {
    renderButton()
    const trigger = screen.getByRole("button", { name: "activity:export.title" })
    expect(trigger).toHaveAttribute("aria-expanded", "false")
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
  })

  it("opens the menu with PDF + PNG items", async () => {
    const user = userEvent.setup()
    renderButton()
    await user.click(screen.getByRole("button", { name: "activity:export.title" }))
    expect(screen.getByRole("menu")).toBeInTheDocument()
    expect(screen.getByText("activity:export.pdf")).toBeInTheDocument()
    expect(screen.getByText("activity:export.png")).toBeInTheDocument()
  })

  it("puts focus on the first export action and supports arrow keys and Escape", async () => {
    const user = userEvent.setup()
    renderButton()
    const trigger = screen.getByRole("button", { name: "activity:export.title" })
    await user.tab()
    await user.keyboard("{Enter}")
    const pdf = screen.getByRole("menuitem", { name: "activity:export.pdf" })
    const png = screen.getByRole("menuitem", { name: "activity:export.png" })
    expect(pdf).toHaveFocus()
    expect(pdf).toHaveAttribute("tabindex", "-1")
    expect(png).toHaveAttribute("tabindex", "-1")
    await user.keyboard("{ArrowDown}")
    expect(png).toHaveFocus()
    await user.keyboard("{ArrowUp}")
    expect(pdf).toHaveFocus()
    await user.keyboard("{Escape}")
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it("does not steal focus on Escape outside the export control", async () => {
    const user = userEvent.setup()
    render(
      <>
        <ActivityExportButton contentRef={{ current: document.createElement("div") }} />
        <button type="button">Adjacent control</button>
      </>
    )
    await user.click(screen.getByRole("button", { name: "activity:export.title" }))
    const adjacent = screen.getByRole("button", { name: "Adjacent control" })
    act(() => adjacent.focus())
    expect(adjacent).toHaveFocus()
    await user.keyboard("{Escape}")
    expect(adjacent).toHaveFocus()
  })

  it("opens with Space and dismisses when Tab moves to the next control", async () => {
    const user = userEvent.setup()
    render(
      <>
        <ActivityExportButton contentRef={{ current: document.createElement("div") }} />
        <button type="button">Adjacent control</button>
      </>
    )
    await user.tab()
    await user.keyboard(" ")
    expect(screen.getByRole("menuitem", { name: "activity:export.pdf" })).toHaveFocus()
    await user.tab()
    expect(screen.getByRole("button", { name: "Adjacent control" })).toHaveFocus()
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
  })

  it("exports as PDF and shows success feedback", async () => {
    const user = userEvent.setup()
    renderButton()
    await user.click(screen.getByRole("button", { name: "activity:export.title" }))
    await user.click(screen.getByText("activity:export.pdf"))
    expect(exportMock.pdf).toHaveBeenCalledWith(expect.any(HTMLDivElement), "activity:title")
    await waitFor(() => expect(screen.getByText("activity:export.success")).toBeInTheDocument())
  })

  it("exports as PNG", async () => {
    const user = userEvent.setup()
    renderButton()
    await user.click(screen.getByRole("button", { name: "activity:export.title" }))
    await user.click(screen.getByText("activity:export.png"))
    expect(exportMock.png).toHaveBeenCalledOnce()
  })

  it("shows error feedback when the export rejects", async () => {
    exportMock.pdf.mockRejectedValueOnce(new Error("boom"))
    const user = userEvent.setup()
    renderButton()
    await user.click(screen.getByRole("button", { name: "activity:export.title" }))
    await user.click(screen.getByText("activity:export.pdf"))
    await waitFor(() => expect(screen.getByText("activity:export.error")).toBeInTheDocument())
  })

  it("uses translated error feedback when a failed export has no message", async () => {
    exportMock.pdf.mockResolvedValueOnce({ success: false })
    const user = userEvent.setup()
    renderButton()
    await user.click(screen.getByRole("button", { name: "activity:export.title" }))
    await user.click(screen.getByText("activity:export.pdf"))

    await waitFor(() => expect(screen.getByText("activity:export.error")).toBeInTheDocument())
  })

  it("shows the exporting state while a slow export is pending", async () => {
    let resolveExport: (v: { success: boolean }) => void = () => {}
    exportMock.pdf.mockReturnValueOnce(
      new Promise<{ success: boolean }>((resolve) => {
        resolveExport = resolve
      })
    )
    const user = userEvent.setup()
    renderButton()
    await user.click(screen.getByRole("button", { name: "activity:export.title" }))
    await user.click(screen.getByText("activity:export.pdf"))
    expect(screen.getByText("activity:export.exporting")).toBeInTheDocument()
    const trigger = screen.getByRole("button", { name: "activity:export.title" })
    expect(trigger).toBeDisabled()
    await act(async () => {
      resolveExport({ success: true })
    })
    await waitFor(() => expect(screen.getByText("activity:export.success")).toBeInTheDocument())
    expect(trigger).toHaveFocus()
  })

  it("keeps focus on the next control when a deferred export fails", async () => {
    let rejectExport: (reason: Error) => void = () => {}
    exportMock.pdf.mockReturnValueOnce(
      new Promise((_, reject) => {
        rejectExport = reject
      })
    )
    const user = userEvent.setup()
    render(
      <>
        <ActivityExportButton contentRef={{ current: document.createElement("div") }} />
        <button type="button">Adjacent control</button>
      </>
    )
    await user.click(screen.getByRole("button", { name: "activity:export.title" }))
    await user.click(screen.getByRole("menuitem", { name: "activity:export.pdf" }))
    const adjacent = screen.getByRole("button", { name: "Adjacent control" })
    await user.click(adjacent)
    await act(async () => rejectExport(new Error("failed export")))
    expect(screen.getByText("activity:export.error")).toBeInTheDocument()
    expect(adjacent).toHaveFocus()
  })

  it("clears success feedback after the display interval", async () => {
    vi.useFakeTimers()

    try {
      renderButton()
      fireEvent.click(screen.getByRole("button", { name: "activity:export.title" }))

      await act(async () => {
        fireEvent.click(screen.getByRole("menuitem", { name: "activity:export.pdf" }))
        await Promise.resolve()
      })
      expect(screen.getByText("activity:export.success")).toBeInTheDocument()

      act(() => {
        vi.advanceTimersByTime(3000)
      })
      expect(screen.queryByText("activity:export.success")).not.toBeInTheDocument()
      expect(screen.getByText("activity:export.title")).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it("ignores a synchronous re-entrant export request", async () => {
    const user = userEvent.setup()
    renderButton()
    await user.click(screen.getByRole("button", { name: "activity:export.title" }))
    const pdfItem = screen.getByRole("menuitem", { name: "activity:export.pdf" })

    exportMock.pdf.mockImplementationOnce(() => {
      fireEvent.click(pdfItem)
      return Promise.resolve({ success: true })
    })

    fireEvent.click(pdfItem)

    expect(exportMock.pdf).toHaveBeenCalledOnce()
    await waitFor(() => expect(screen.getByText("activity:export.success")).toBeInTheDocument())
  })

  it("closes the menu on Escape and on outside click", async () => {
    const user = userEvent.setup()
    renderButton()
    await user.click(screen.getByRole("button", { name: "activity:export.title" }))
    expect(screen.getByRole("menu")).toBeInTheDocument()
    fireEvent.mouseDown(screen.getByRole("menu"))
    expect(screen.getByRole("menu")).toBeInTheDocument()
    fireEvent.keyDown(screen.getByRole("menu"), { key: "Shift" })
    expect(screen.getByRole("menu")).toBeInTheDocument()
    await user.keyboard("{Escape}")
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "activity:export.title" }))
    expect(screen.getByRole("menu")).toBeInTheDocument()
    act(() => {
      document.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }))
    })
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
  })

  it("ignores an outside-click callback whose target is not a DOM Node", async () => {
    const addEventListenerSpy = vi.spyOn(document, "addEventListener")
    const user = userEvent.setup()

    try {
      renderButton()
      await user.click(screen.getByRole("button", { name: "activity:export.title" }))
      const mouseDownListener = addEventListenerSpy.mock.calls.find(
        ([eventName]) => eventName === "mousedown"
      )?.[1] as EventListener | undefined
      expect(mouseDownListener).toBeDefined()

      act(() => {
        mouseDownListener?.({ target: new EventTarget() } as unknown as MouseEvent)
      })

      expect(screen.getByRole("menu")).toBeInTheDocument()
    } finally {
      addEventListenerSpy.mockRestore()
    }
  })
})
