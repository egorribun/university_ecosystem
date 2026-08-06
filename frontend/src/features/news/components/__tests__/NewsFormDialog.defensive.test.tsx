import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { createNews, uploadNewsImage } from "@/api/news"
import { NewsFormDialog } from "../NewsFormDialog"

vi.mock("@/api/news", () => ({
  createNews: vi.fn(),
  uploadNewsImage: vi.fn(),
}))

const createNewsMock = vi.mocked(createNews)
const uploadNewsImageMock = vi.mocked(uploadNewsImage)

const renderDialog = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <NewsFormDialog open onClose={vi.fn()} onSuccess={vi.fn()} />
    </QueryClientProvider>
  )
}

describe("NewsFormDialog defensive errors", () => {
  it("uses the translated fallback for a raw non-Error rejection", async () => {
    createNewsMock.mockRejectedValueOnce(42)
    const user = userEvent.setup()
    renderDialog()

    await user.type(screen.getByLabelText(/^Title(?! \()/i), "Raw failure")
    await user.type(screen.getByLabelText(/^News text(?! \()/i), "Content")
    await user.click(screen.getByRole("button", { name: /Publish/i }))

    expect(await screen.findByRole("alert")).toHaveTextContent(
      i18n.t("news:notifications.savedError")
    )
  })

  it("handles a raw Axios response string", async () => {
    createNewsMock.mockRejectedValueOnce({
      isAxiosError: true,
      response: { data: "Raw server failure" },
    })
    const user = userEvent.setup()
    renderDialog()

    await user.type(screen.getByLabelText(/^Title(?! \()/i), "Raw Axios failure")
    await user.type(screen.getByLabelText(/^News text(?! \()/i), "Content")
    await user.click(screen.getByRole("button", { name: /Publish/i }))

    expect(await screen.findByRole("alert")).toHaveTextContent("Raw server failure")
  })

  it("submits an empty uploaded URL without losing the form flow", async () => {
    uploadNewsImageMock.mockResolvedValueOnce("")
    createNewsMock.mockResolvedValueOnce({} as never)
    const user = userEvent.setup()
    renderDialog()

    await user.type(screen.getByLabelText(/^Title(?! \()/i), "No URL")
    await user.type(screen.getByLabelText(/^News text(?! \()/i), "Content")
    await user.upload(
      document.querySelector('input[type="file"]') as HTMLInputElement,
      new File(["image"], "cover.png", { type: "image/png" })
    )
    await user.click(screen.getByRole("button", { name: /Publish/i }))

    await waitFor(() =>
      expect(createNewsMock).toHaveBeenCalledWith(expect.objectContaining({ image_url: "" }))
    )
  })

  it("renders empty labels when translations are unavailable", () => {
    const translationSpy = vi.spyOn(i18n, "t").mockReturnValue(undefined as never)

    try {
      renderDialog()
      expect(screen.getByRole("dialog")).toBeInTheDocument()
    } finally {
      translationSpy.mockRestore()
    }
  })

  it("uses the hardcoded save fallback when its translation is unavailable", async () => {
    const translationSpy = vi.spyOn(i18n, "t").mockReturnValue(undefined as never)
    createNewsMock.mockRejectedValueOnce(42)
    const user = userEvent.setup()

    try {
      renderDialog()
      await user.type(document.getElementById("news-title") as HTMLInputElement, "Raw failure")
      await user.type(document.getElementById("news-content") as HTMLTextAreaElement, "Content")
      await user.click(document.querySelector('button[type="submit"]') as HTMLButtonElement)

      expect(await screen.findByRole("alert")).toHaveTextContent("Failed to save the news")
    } finally {
      translationSpy.mockRestore()
    }
  })
})
