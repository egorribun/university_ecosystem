import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))
// Module-mock @/api/news directly so updateNews / uploadNewsImage never reach MSW.
const updateNews = vi.fn((..._a: unknown[]) => Promise.resolve({ data: { id: "news-1" } }))
const uploadNewsImage = vi.fn((..._a: unknown[]) => Promise.resolve("https://cdn/uploaded.png"))
vi.mock("@/api/news", () => ({
  updateNews: (...a: unknown[]) => updateNews(...a),
  uploadNewsImage: (...a: unknown[]) => uploadNewsImage(...a),
}))

import { NewsDetailEditDialog } from "@/components/news/NewsDetailEditDialog"

const initialData = {
  title: "Запуск новой кампусной экосистемы",
  content: "Единая платформа: расписание, новости, события и мессенджер.",
  title_en: "Launching the new campus ecosystem",
  content_en: "A unified platform for schedule, news, events, and messenger.",
  image_url: "https://picsum.photos/seed/news-detail-edit/800/400",
}

const baseProps = {
  open: true,
  onClose: vi.fn(),
  newsId: "news-1",
  language: "ru",
  initialData,
  onSuccess: vi.fn(),
  onError: vi.fn(),
}

function renderDialog(props = baseProps) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const invalidateSpy = vi.spyOn(client, "invalidateQueries").mockResolvedValue(undefined)
  const setDataSpy = vi.spyOn(client, "setQueryData")
  const utils = render(
    <QueryClientProvider client={client}>
      <NewsDetailEditDialog {...props} />
    </QueryClientProvider>
  )
  return { ...utils, client, invalidateSpy, setDataSpy }
}

// The Dialog portals to document.body, so query the file input from the document.
function getFileInput(): HTMLInputElement {
  return document.querySelector('input[type="file"]') as HTMLInputElement
}

beforeEach(() => {
  // jsdom doesn't implement object URLs — stub them so handleImageChange / resetPreview work.
  globalThis.URL.createObjectURL = vi.fn(() => "blob:mock-preview")
  globalThis.URL.revokeObjectURL = vi.fn()
})

afterEach(() => {
  vi.clearAllMocks()
})

describe("NewsDetailEditDialog branches", () => {
  it("edits content / title_en / content_en fields (onChange lines 149, 163, 173)", async () => {
    const user = userEvent.setup()
    renderDialog()

    const content = screen.getByDisplayValue(initialData.content)
    await user.type(content, "!")
    expect((content as HTMLTextAreaElement).value).toBe(`${initialData.content}!`)

    const titleEn = screen.getByDisplayValue(initialData.title_en)
    await user.type(titleEn, "X")
    expect((titleEn as HTMLInputElement).value).toBe(`${initialData.title_en}X`)

    const contentEn = screen.getByDisplayValue(initialData.content_en)
    await user.type(contentEn, "Y")
    expect((contentEn as HTMLTextAreaElement).value).toBe(`${initialData.content_en}Y`)
  })

  it("uploads an image then resets the preview (handleImageChange 95-100 + resetPreview 81-84)", async () => {
    const user = userEvent.setup()
    renderDialog()
    const fileInput = getFileInput()
    const file = new File(["x"], "photo.png", { type: "image/png" })

    await user.upload(fileInput, file)

    // createObjectURL drives the preview; the upload label flips to "changePhoto" (line 187 truthy)
    expect(globalThis.URL.createObjectURL).toHaveBeenCalledWith(file)
    expect(screen.getByText("common:buttons.changePhoto")).toBeInTheDocument()

    // Reset button only renders once previewUrl is set (cold-branch 207 truthy + lines 208-215)
    const resetBtn = screen.getByRole("button", { name: "common:buttons.reset" })
    await user.click(resetBtn)

    // resetPreview revokes the URL (lines 82-83) and clears the input
    expect(globalThis.URL.revokeObjectURL).toHaveBeenCalledWith("blob:mock-preview")
    expect(screen.queryByRole("button", { name: "common:buttons.reset" })).not.toBeInTheDocument()
    expect(fileInput.value).toBe("")
  })

  it("revokes an existing preview when a SECOND image is chosen (line 97 truthy branch)", async () => {
    const user = userEvent.setup()
    renderDialog()
    const fileInput = getFileInput()

    await user.upload(fileInput, new File(["a"], "first.png", { type: "image/png" }))
    ;(globalThis.URL.revokeObjectURL as ReturnType<typeof vi.fn>).mockClear()

    await user.upload(fileInput, new File(["b"], "second.png", { type: "image/png" }))
    // previewUrl was already set → handleImageChange revokes the old one before creating a new
    expect(globalThis.URL.revokeObjectURL).toHaveBeenCalledWith("blob:mock-preview")
  })

  it("saves WITHOUT a new image — skips uploadNewsImage (handleSave 105-119, line 108 false)", async () => {
    const user = userEvent.setup()
    const onSuccess = vi.fn()
    const onClose = vi.fn()
    const { setDataSpy, invalidateSpy } = renderDialog({ ...baseProps, onSuccess, onClose })

    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))

    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith("news:notifications.updated"))
    expect(uploadNewsImage).not.toHaveBeenCalled()
    expect(updateNews).toHaveBeenCalledWith("news-1", {
      title: initialData.title,
      content: initialData.content,
      title_en: initialData.title_en,
      content_en: initialData.content_en,
      image_url: initialData.image_url,
    })
    expect(setDataSpy).toHaveBeenCalledWith(["news", "news-1", "ru"], { id: "news-1" })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["news", "list"] })
    // handleSave → handleClose → onClose (line 119)
    expect(onClose).toHaveBeenCalled()
  })

  it("saves WITH a new image — uploads first (handleSave line 108 truthy)", async () => {
    const user = userEvent.setup()
    const onSuccess = vi.fn()
    renderDialog({ ...baseProps, onSuccess })
    const fileInput = getFileInput()
    const file = new File(["img"], "new.png", { type: "image/png" })

    await user.upload(fileInput, file)
    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))

    await waitFor(() => expect(uploadNewsImage).toHaveBeenCalledWith(file))
    // finalImageUrl comes from the upload result, not initialData.image_url
    expect(updateNews).toHaveBeenCalledWith(
      "news-1",
      expect.objectContaining({ image_url: "https://cdn/uploaded.png" })
    )
    expect(onSuccess).toHaveBeenCalledWith("news:notifications.updated")
  })

  it("calls onError when updateNews rejects (handleSave catch 120-121)", async () => {
    const user = userEvent.setup()
    const onError = vi.fn()
    const onSuccess = vi.fn()
    updateNews.mockRejectedValueOnce(new Error("network"))
    renderDialog({ ...baseProps, onError, onSuccess })

    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))

    await waitFor(() => expect(onError).toHaveBeenCalledWith("news:notifications.savedError"))
    expect(onSuccess).not.toHaveBeenCalled()
    // After a failed save the dialog stays open (handleClose not reached) → save button re-enabled
    expect(screen.getByRole("button", { name: "common:buttons.save" })).toBeEnabled()
  })

  it("syncs editData from initialData when the dialog re-opens (effect line 69)", () => {
    const { rerender } = renderDialog({ ...baseProps, open: false })
    const nextData = { ...initialData, title: "Reopened title" }
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <NewsDetailEditDialog {...baseProps} open initialData={nextData} />
      </QueryClientProvider>
    )
    expect(screen.getByDisplayValue("Reopened title")).toBeInTheDocument()
  })

  it("revokes the preview URL on unmount when one exists (cleanup cold-branch line 75)", async () => {
    const user = userEvent.setup()
    const { unmount } = renderDialog()
    await user.upload(getFileInput(), new File(["u"], "u.png", { type: "image/png" }))
    ;(globalThis.URL.revokeObjectURL as ReturnType<typeof vi.fn>).mockClear()

    unmount()
    expect(globalThis.URL.revokeObjectURL).toHaveBeenCalledWith("blob:mock-preview")
  })

  it("ignores an image change event with no file selected (line 96 early return)", () => {
    renderDialog()
    const fileInput = getFileInput()
    // The input has an empty FileList by default → handleImageChange returns early (no preview)
    fireEvent.change(fileInput)
    expect(globalThis.URL.createObjectURL).not.toHaveBeenCalled()
    expect(screen.queryByRole("button", { name: "common:buttons.reset" })).not.toBeInTheDocument()
  })
})
