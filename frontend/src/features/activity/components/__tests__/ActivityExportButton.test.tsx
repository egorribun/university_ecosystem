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
    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }))
    })
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "activity:export.title" }))
    expect(screen.getByRole("menu")).toBeInTheDocument()
    act(() => {
      document.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }))
    })
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
  })
})
