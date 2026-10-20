import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ComponentProps } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const translationMocks = vi.hoisted(() => ({
  returnUndefined: false,
  namespaceCalls: [] as unknown[],
  tCalls: [] as Array<{ key: string; options?: unknown }>,
}))

const apiMocks = vi.hoisted(() => ({
  fetchNewsItem: vi.fn(),
  updateNews: vi.fn(),
  uploadNewsImage: vi.fn(),
}))

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: (namespaces: unknown) => {
    translationMocks.namespaceCalls.push(namespaces)
    return {
      t: (key: string, options?: unknown) => {
        translationMocks.tCalls.push({ key, options })
        return translationMocks.returnUndefined ? undefined : key
      },
      i18n: { language: "en", changeLanguage: () => Promise.resolve() },
    }
  },
}))
vi.mock("@/api/news", () => ({
  fetchNewsItem: apiMocks.fetchNewsItem,
  updateNews: apiMocks.updateNews,
  uploadNewsImage: apiMocks.uploadNewsImage,
}))
vi.mock("@/components/media/SmartImage", () => ({
  default: ({ srcRaw, alt, className }: { srcRaw?: string; alt?: string; className?: string }) => (
    <img data-testid="edit-preview" src={srcRaw} alt={alt} className={className} />
  ),
}))

import {
  getSelectedNewsImageFile,
  NewsDetailEditDialog,
} from "@/components/news/NewsDetailEditDialog"

const initialData = {
  title: "Запуск новой кампусной экосистемы",
  content: "Единая платформа: расписание, новости, события и мессенджер.",
  title_en: "Launching the new campus ecosystem",
  content_en: "A unified platform for schedule, news, events, and messenger.",
  image_url: "https://picsum.photos/seed/news-detail-edit/800/400",
}

const makeProps = (
  overrides: Partial<ComponentProps<typeof NewsDetailEditDialog>> = {}
): ComponentProps<typeof NewsDetailEditDialog> => ({
  open: true,
  onClose: vi.fn(),
  newsId: "news-contract",
  language: "ru",
  initialData,
  onSuccess: vi.fn(),
  onError: vi.fn(),
  ...overrides,
})

function renderDialog(overrides: Partial<ComponentProps<typeof NewsDetailEditDialog>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = render(
    <QueryClientProvider client={client}>
      <NewsDetailEditDialog {...makeProps(overrides)} />
    </QueryClientProvider>
  )
  return { ...view, client }
}

describe("NewsDetailEditDialog mutation contracts", () => {
  beforeEach(() => {
    translationMocks.returnUndefined = false
    translationMocks.namespaceCalls = []
    translationMocks.tCalls = []
    apiMocks.fetchNewsItem.mockReset()
    apiMocks.updateNews.mockReset().mockResolvedValue({ data: { ...initialData } })
    apiMocks.uploadNewsImage.mockReset().mockResolvedValue("https://example.test/uploaded.png")
  })

  it("preserves namespaces, required markers, field constraints, and preview semantics", () => {
    renderDialog()

    expect(translationMocks.namespaceCalls).toContainEqual(["news", "common"])
    expect(screen.getByText("news:dialogs.edit.title")).toBeInTheDocument()

    const titleLabel = document.querySelector<HTMLLabelElement>('label[for="edit-title"]')!
    const contentLabel = document.querySelector<HTMLLabelElement>('label[for="edit-content"]')!
    const titleEnLabel = document.querySelector<HTMLLabelElement>('label[for="edit-title-en"]')!
    const contentEnLabel = document.querySelector<HTMLLabelElement>('label[for="edit-content-en"]')!
    expect(titleLabel.textContent?.trim()).toBe("news:form.title*")
    expect(contentLabel.textContent?.trim()).toBe("news:form.content*")
    expect(titleEnLabel.textContent?.trim()).toBe("news:form.title_en")
    expect(contentEnLabel.textContent?.trim()).toBe("news:form.content_en")

    const title = screen.getByDisplayValue(initialData.title)
    const content = screen.getByDisplayValue(initialData.content)
    const titleEn = screen.getByDisplayValue(initialData.title_en)
    const contentEn = screen.getByDisplayValue(initialData.content_en)
    expect(title).toHaveAttribute("id", "edit-title")
    expect(title).toHaveAttribute("maxLength", "100")
    expect(content).toHaveAttribute("id", "edit-content")
    expect(content).toHaveAttribute("maxLength", "3000")
    expect(content).toHaveAttribute("rows", "6")
    expect(titleEn).toHaveAttribute("id", "edit-title-en")
    expect(titleEn).toHaveAttribute("maxLength", "100")
    expect(contentEn).toHaveAttribute("id", "edit-content-en")
    expect(contentEn).toHaveAttribute("maxLength", "3000")
    expect(contentEn).toHaveAttribute("rows", "6")

    const uploadButton = screen.getByText("common:buttons.uploadPhoto").closest("label")!
    expect(uploadButton).toHaveClass("w-full", "sm:w-auto")
    expect(uploadButton).not.toHaveAttribute("aria-disabled", "true")
    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!
    expect(fileInput).toHaveAttribute("accept", "image/*")
    expect(fileInput).toHaveAttribute("hidden")
    expect(screen.getByTestId("edit-preview")).toHaveAttribute("alt", "news:alt.editPreview")
    expect(screen.getByTestId("edit-preview")).toHaveClass("h-14", "w-28", "object-cover")
  })

  it("synchronizes replacement data on open and keeps callback dependencies fresh", async () => {
    const firstClose = vi.fn()
    const nextClose = vi.fn()
    const view = renderDialog({ onClose: firstClose })
    const replacement = {
      ...initialData,
      title: "Replacement title",
      content: "Replacement content",
      title_en: "",
      content_en: "",
      image_url: "",
    }

    view.rerender(
      <QueryClientProvider client={view.client}>
        <NewsDetailEditDialog
          {...makeProps({ open: true, initialData: replacement, onClose: nextClose })}
        />
      </QueryClientProvider>
    )
    await waitFor(() => {
      expect(screen.getByDisplayValue(replacement.title)).toBeInTheDocument()
      expect(screen.getByDisplayValue(replacement.content)).toBeInTheDocument()
    })
    expect(screen.getByLabelText("news:form.title_en")).toHaveValue("")
    expect(screen.getByLabelText("news:form.content_en")).toHaveValue("")
    expect(screen.queryByTestId("edit-preview")).not.toBeInTheDocument()

    await userEvent.setup().click(screen.getByRole("button", { name: "common:buttons.cancel" }))
    expect(firstClose).not.toHaveBeenCalled()
    expect(nextClose).toHaveBeenCalledOnce()
  })

  it("does not synchronize replacement data while the dialog is closed", async () => {
    const replacement = {
      ...initialData,
      title: "Closed replacement",
      content: "Closed content",
    }
    const view = renderDialog({ open: false })
    view.rerender(
      <QueryClientProvider client={view.client}>
        <NewsDetailEditDialog {...makeProps({ open: false, initialData: replacement })} />
      </QueryClientProvider>
    )
    expect(screen.queryByDisplayValue(replacement.title)).not.toBeInTheDocument()
    expect(screen.queryByDisplayValue(replacement.content)).not.toBeInTheDocument()
    expect(screen.queryByText("news:dialogs.edit.title")).not.toBeInTheDocument()
  })

  it("prioritizes preview images, safely handles empty files, and cleans URLs exactly once", async () => {
    const user = userEvent.setup()
    const createObjectURL = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:detail-one")
    const revokeObjectURL = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined)
    const view = renderDialog()
    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!
    const firstFile = new File(["first"], "first.png", { type: "image/png" })
    const secondFile = new File(["second"], "second.png", { type: "image/png" })

    fireEvent.change(fileInput, { target: { files: [firstFile] } })
    await waitFor(() => expect(createObjectURL).toHaveBeenCalledWith(firstFile))
    expect(screen.getByTestId("edit-preview")).toHaveAttribute("src", "blob:detail-one")
    expect(screen.getByText("common:buttons.changePhoto")).toBeInTheDocument()

    createObjectURL.mockReturnValue("blob:detail-two")
    fireEvent.change(fileInput, { target: { files: [secondFile] } })
    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith("blob:detail-one"))

    fireEvent.change(fileInput, { target: { files: [] } })
    expect(screen.getByTestId("edit-preview")).toHaveAttribute("src", "blob:detail-two")
    Object.defineProperty(fileInput, "files", { configurable: true, value: null })
    expect(() => fireEvent.change(fileInput)).not.toThrow()

    await user.click(screen.getByRole("button", { name: "common:buttons.reset" }))
    await waitFor(() =>
      expect(screen.getByTestId("edit-preview")).toHaveAttribute("src", initialData.image_url)
    )
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:detail-two")
    view.unmount()
    expect(revokeObjectURL).not.toHaveBeenCalledWith(null)

    createObjectURL.mockRestore()
    revokeObjectURL.mockRestore()
  })

  it("normalizes missing and empty file selections before preview work", () => {
    const file = new File(["image"], "image.png", { type: "image/png" })

    expect(getSelectedNewsImageFile(undefined)).toBeUndefined()
    expect(getSelectedNewsImageFile(null)).toBeUndefined()
    expect(getSelectedNewsImageFile([] as unknown as FileList)).toBeUndefined()
    expect(getSelectedNewsImageFile([file] as unknown as FileList)).toBe(file)
  })

  it("shows deterministic saving state and updates the cache with edited fields", async () => {
    const user = userEvent.setup()
    let resolveUpdate: (value: { data: typeof initialData }) => void = () => undefined
    apiMocks.updateNews.mockImplementation(
      () =>
        new Promise<{ data: typeof initialData }>((resolve) => {
          resolveUpdate = resolve
        })
    )
    const onSuccess = vi.fn()
    const onClose = vi.fn()
    const { client } = renderDialog({ onSuccess, onClose })
    const setQueryData = vi.spyOn(client, "setQueryData")
    const invalidateQueries = vi.spyOn(client, "invalidateQueries").mockResolvedValue(undefined)
    const title = screen.getByDisplayValue(initialData.title)
    const content = screen.getByDisplayValue(initialData.content)
    await user.clear(title)
    await user.type(title, "Updated title")
    await user.clear(content)
    await user.type(content, "Updated content")
    const saveButton = screen.getByRole("button", { name: "common:buttons.save" })
    await user.click(saveButton)

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "common:buttons.saving" })).toBeInTheDocument()
    )
    expect(screen.getByRole("button", { name: "common:buttons.saving" })).toBeDisabled()
    expect(screen.getByText("common:buttons.uploadPhoto").closest("label")).toHaveAttribute(
      "aria-disabled",
      "true"
    )
    expect(apiMocks.updateNews).toHaveBeenCalledWith("news-contract", {
      title: "Updated title",
      content: "Updated content",
      title_en: initialData.title_en,
      content_en: initialData.content_en,
      image_url: initialData.image_url,
    })

    resolveUpdate({ data: { ...initialData, title: "Updated title", content: "Updated content" } })
    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith("news:notifications.updated"))
    expect(setQueryData).toHaveBeenCalledWith(
      ["news", "news-contract", "ru"],
      expect.objectContaining({ title: "Updated title" })
    )
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["news", "list"] })
    expect(onClose).toHaveBeenCalledOnce()
  })

  it("loads Russian source fields before saving from the English editor", async () => {
    const user = userEvent.setup()
    const russianSource = {
      id: "news-contract",
      title: "Русский оригинал",
      content: "Текст на русском языке.",
      title_en: "English original",
      content_en: "English source body.",
      image_url: "https://example.test/source.png",
    }
    apiMocks.fetchNewsItem.mockResolvedValue({ status: 200, data: russianSource })
    renderDialog({
      language: "en",
      initialData: {
        ...initialData,
        title: "Localized English title",
        content: "Localized English body.",
      },
    })

    await waitFor(() => expect(screen.getByDisplayValue(russianSource.title)).toBeInTheDocument())
    expect(screen.getByDisplayValue(russianSource.content)).toBeInTheDocument()
    expect(screen.getByDisplayValue(russianSource.title_en)).toBeInTheDocument()
    expect(screen.getByDisplayValue(russianSource.content_en)).toBeInTheDocument()
    expect(apiMocks.fetchNewsItem).toHaveBeenCalledWith(
      "news-contract",
      expect.objectContaining({ language: "ru", signal: expect.any(AbortSignal) })
    )

    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))
    await waitFor(() => expect(apiMocks.updateNews).toHaveBeenCalledOnce())
    expect(apiMocks.updateNews).toHaveBeenCalledWith("news-contract", {
      title: russianSource.title,
      content: russianSource.content,
      title_en: russianSource.title_en,
      content_en: russianSource.content_en,
      image_url: russianSource.image_url,
    })
  })

  it("keeps saving disabled while the Russian source request is pending", async () => {
    let resolveSource!: (value: { status: number; data: Record<string, string> }) => void
    apiMocks.fetchNewsItem.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveSource = resolve
      })
    )
    renderDialog({ language: "en" })

    expect(screen.getByRole("status")).toHaveTextContent("common:statuses.loading")
    const save = screen.getByRole("button", { name: "common:buttons.save" })
    expect(save).toBeDisabled()
    fireEvent.click(save)
    expect(apiMocks.updateNews).not.toHaveBeenCalled()

    await act(async () => {
      resolveSource({ status: 200, data: { ...initialData } })
    })
    await waitFor(() => expect(save).toBeEnabled())
  })

  it("fails closed when the Russian source request rejects", async () => {
    apiMocks.fetchNewsItem.mockRejectedValueOnce(new Error("source unavailable"))
    renderDialog({ language: "en" })

    expect(await screen.findByRole("alert")).toHaveTextContent("common:errors.generic")
    const save = screen.getByRole("button", { name: "common:buttons.save" })
    expect(save).toBeDisabled()
    fireEvent.click(save)
    expect(apiMocks.updateNews).not.toHaveBeenCalled()
  })

  it("fails closed when the Russian source request returns not-modified", async () => {
    apiMocks.fetchNewsItem.mockResolvedValueOnce({ status: 304, data: undefined })
    renderDialog({ language: "en" })

    expect(await screen.findByRole("alert")).toHaveTextContent("common:errors.generic")
    const save = screen.getByRole("button", { name: "common:buttons.save" })
    expect(save).toBeDisabled()
    fireEvent.click(save)
    expect(apiMocks.updateNews).not.toHaveBeenCalled()
  })

  it("ignores an aborted Russian source response after the news ID changes", async () => {
    const requests: Array<{
      newsId: string
      signal: AbortSignal
      resolve: (value: { status: number; data: Record<string, string> }) => void
    }> = []
    apiMocks.fetchNewsItem.mockImplementation(
      (newsId: string, options: { signal: AbortSignal }) =>
        new Promise<{ status: number; data: Record<string, string> }>((resolve) => {
          requests.push({ newsId, signal: options.signal, resolve })
        })
    )
    const { rerender, client } = renderDialog({ language: "en", newsId: "news-old" })

    expect(requests).toHaveLength(1)
    rerender(
      <QueryClientProvider client={client}>
        <NewsDetailEditDialog {...makeProps({ language: "en", newsId: "news-new" })} />
      </QueryClientProvider>
    )
    expect(requests).toHaveLength(2)
    expect(requests[0]?.newsId).toBe("news-old")
    expect(requests[0]?.signal.aborted).toBe(true)
    expect(requests[1]?.newsId).toBe("news-new")

    await act(async () => {
      requests[0]?.resolve({
        status: 200,
        data: { ...initialData, title: "Stale Russian title", content: "Stale Russian body" },
      })
    })
    expect(screen.queryByDisplayValue("Stale Russian title")).not.toBeInTheDocument()

    await act(async () => {
      requests[1]?.resolve({
        status: 200,
        data: { ...initialData, title: "Current Russian title", content: "Current Russian body" },
      })
    })
    await waitFor(() =>
      expect(screen.getByDisplayValue("Current Russian title")).toBeInTheDocument()
    )
    expect(screen.queryByDisplayValue("Stale Russian title")).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "common:buttons.save" }))
    await waitFor(() => expect(apiMocks.updateNews).toHaveBeenCalledOnce())
    expect(apiMocks.updateNews).toHaveBeenCalledWith(
      "news-new",
      expect.objectContaining({
        title: "Current Russian title",
        content: "Current Russian body",
      })
    )
  })

  it("renders no image block without an image and preserves exact fallback labels", () => {
    const { rerender, client } = renderDialog({ initialData: { ...initialData, image_url: "" } })
    expect(screen.queryByTestId("edit-preview")).not.toBeInTheDocument()

    translationMocks.returnUndefined = true
    rerender(
      <QueryClientProvider client={client}>
        <NewsDetailEditDialog {...makeProps({ initialData: { ...initialData, image_url: "" } })} />
      </QueryClientProvider>
    )
    const titleLabel = document.querySelector<HTMLLabelElement>('label[for="edit-title"]')!
    const contentLabel = document.querySelector<HTMLLabelElement>('label[for="edit-content"]')!
    const titleEnLabel = document.querySelector<HTMLLabelElement>('label[for="edit-title-en"]')!
    const contentEnLabel = document.querySelector<HTMLLabelElement>('label[for="edit-content-en"]')!
    expect(titleLabel.textContent?.trim()).toBe("*")
    expect(contentLabel.textContent?.trim()).toBe("*")
    expect(titleEnLabel.textContent?.trim()).toBe("")
    expect(contentEnLabel.textContent?.trim()).toBe("")
    expect(document.querySelector("label.block.text-sm.font-semibold")).toHaveTextContent("")
  })

  it("does not revoke a missing preview during close or unmount", () => {
    const revokeObjectURL = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined)
    const { unmount } = renderDialog({ initialData: { ...initialData, image_url: "" } })
    expect(() => unmount()).not.toThrow()
    expect(revokeObjectURL).not.toHaveBeenCalled()
    revokeObjectURL.mockRestore()
  })

  it("keeps required field validation, image labels, and whitespace saves deterministic", async () => {
    const user = userEvent.setup()
    const onError = vi.fn()
    renderDialog({ onError })

    expect(screen.getByText("news:form.image")).toBeInTheDocument()
    const title = screen.getByDisplayValue(initialData.title)
    const content = screen.getByDisplayValue(initialData.content)
    await user.clear(title)
    await user.type(title, "   ")
    await user.clear(content)
    await user.type(content, "   ")
    expect(screen.getByRole("button", { name: "common:buttons.save" })).toBeDisabled()

    // Closing without a selected image must not revoke a null preview URL.
    const revokeObjectURL = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined)
    await user.click(screen.getByRole("button", { name: "common:buttons.cancel" }))
    expect(revokeObjectURL).not.toHaveBeenCalled()
    revokeObjectURL.mockRestore()
    expect(onError).not.toHaveBeenCalled()
  })

  it("blocks saving when only the title or only the content is blank", async () => {
    const user = userEvent.setup()
    renderDialog()
    const title = screen.getByDisplayValue(initialData.title)
    const content = screen.getByDisplayValue(initialData.content)
    const save = () => screen.getByRole("button", { name: "common:buttons.save" })

    await user.clear(title)
    await user.type(title, "   ")
    expect(save()).toBeDisabled()

    await user.type(title, "Title")
    await user.clear(content)
    await user.type(content, "   ")
    expect(save()).toBeDisabled()

    await user.type(content, "Body")
    expect(save()).toBeEnabled()
  })

  it("forgets a reset image so saving keeps the current image without uploading", async () => {
    const user = userEvent.setup()
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:reset-me")
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined)
    renderDialog()
    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!
    fireEvent.change(fileInput, {
      target: { files: [new File(["x"], "x.png", { type: "image/png" })] },
    })
    expect(await screen.findByText("common:buttons.changePhoto")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "common:buttons.reset" }))
    expect(screen.getByText("common:buttons.uploadPhoto")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))

    await waitFor(() => expect(apiMocks.updateNews).toHaveBeenCalledOnce())
    expect(apiMocks.uploadNewsImage).not.toHaveBeenCalled()
    expect(apiMocks.updateNews).toHaveBeenCalledWith(
      "news-contract",
      expect.objectContaining({ image_url: initialData.image_url })
    )
    vi.restoreAllMocks()
  })

  it("discards a picked image when the dialog is cancelled and reopened", async () => {
    const user = userEvent.setup()
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:cancelled")
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined)
    const view = renderDialog()
    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!
    fireEvent.change(fileInput, {
      target: { files: [new File(["x"], "x.png", { type: "image/png" })] },
    })
    expect(await screen.findByText("common:buttons.changePhoto")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "common:buttons.cancel" }))
    view.rerender(
      <QueryClientProvider client={view.client}>
        <NewsDetailEditDialog {...makeProps({ open: false })} />
      </QueryClientProvider>
    )
    view.rerender(
      <QueryClientProvider client={view.client}>
        <NewsDetailEditDialog {...makeProps({ open: true })} />
      </QueryClientProvider>
    )

    expect(await screen.findByText("common:buttons.uploadPhoto")).toBeInTheDocument()
    expect(screen.getByTestId("edit-preview")).toHaveAttribute("src", initialData.image_url)
    expect(screen.queryByRole("button", { name: "common:buttons.reset" })).not.toBeInTheDocument()
    vi.restoreAllMocks()
  })

  it("preserves dirty text through a same-item refresh and saves the draft", async () => {
    const user = userEvent.setup()
    const view = renderDialog()

    try {
      const draft = {
        ...initialData,
        title: "Unsaved draft title",
        content: "Unsaved draft content",
      }
      fireEvent.change(screen.getByDisplayValue(initialData.title), {
        target: { value: draft.title },
      })
      fireEvent.change(screen.getByDisplayValue(initialData.content), {
        target: { value: draft.content },
      })
      expect(screen.getByDisplayValue(draft.title)).toHaveValue(draft.title)
      expect(screen.getByDisplayValue(draft.content)).toHaveValue(draft.content)

      const refreshed = {
        ...initialData,
        title: "Refreshed server title",
        content: "Refreshed server content",
      }
      view.rerender(
        <QueryClientProvider client={view.client}>
          <NewsDetailEditDialog {...makeProps({ initialData: refreshed })} />
        </QueryClientProvider>
      )

      expect(screen.getByDisplayValue(draft.title)).toHaveValue(draft.title)
      expect(screen.getByDisplayValue(draft.content)).toHaveValue(draft.content)
      expect(screen.queryByDisplayValue(refreshed.title)).not.toBeInTheDocument()
      expect(screen.queryByDisplayValue(refreshed.content)).not.toBeInTheDocument()

      await user.click(screen.getByRole("button", { name: "common:buttons.save" }))
      await waitFor(() => expect(apiMocks.updateNews).toHaveBeenCalledOnce())
      expect(apiMocks.updateNews).toHaveBeenCalledWith("news-contract", draft)
      expect(apiMocks.fetchNewsItem).not.toHaveBeenCalled()
      expect(apiMocks.uploadNewsImage).not.toHaveBeenCalled()
    } finally {
      view.unmount()
      view.client.clear()
    }
  })

  it("discards dirty text on cancel and reloads current data on reopen", async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    const view = renderDialog({ onClose })

    try {
      fireEvent.change(screen.getByDisplayValue(initialData.title), {
        target: { value: "Cancelled draft title" },
      })
      fireEvent.change(screen.getByDisplayValue(initialData.content), {
        target: { value: "Cancelled draft content" },
      })

      await user.click(screen.getByRole("button", { name: "common:buttons.cancel" }))
      expect(onClose).toHaveBeenCalledOnce()
      expect(apiMocks.updateNews).not.toHaveBeenCalled()
      view.rerender(
        <QueryClientProvider client={view.client}>
          <NewsDetailEditDialog {...makeProps({ open: false, onClose })} />
        </QueryClientProvider>
      )

      const replacement = {
        ...initialData,
        title: "Current title on reopen",
        content: "Current content on reopen",
      }
      view.rerender(
        <QueryClientProvider client={view.client}>
          <NewsDetailEditDialog {...makeProps({ open: true, onClose, initialData: replacement })} />
        </QueryClientProvider>
      )

      expect(await screen.findByDisplayValue(replacement.title)).toHaveValue(replacement.title)
      expect(screen.getByDisplayValue(replacement.content)).toHaveValue(replacement.content)
      expect(screen.queryByDisplayValue("Cancelled draft title")).not.toBeInTheDocument()
      expect(screen.queryByDisplayValue("Cancelled draft content")).not.toBeInTheDocument()

      await user.click(screen.getByRole("button", { name: "common:buttons.save" }))
      await waitFor(() => expect(apiMocks.updateNews).toHaveBeenCalledOnce())
      expect(apiMocks.updateNews).toHaveBeenCalledWith("news-contract", replacement)
    } finally {
      view.unmount()
      view.client.clear()
    }
  })

  it("resets a dirty open form when switching to a different news item", async () => {
    const user = userEvent.setup()
    const view = renderDialog()

    try {
      fireEvent.change(screen.getByDisplayValue(initialData.title), {
        target: { value: "Previous item draft title" },
      })
      fireEvent.change(screen.getByDisplayValue(initialData.content), {
        target: { value: "Previous item draft content" },
      })

      const replacement = {
        ...initialData,
        title: "Different item title",
        content: "Different item content",
      }
      view.rerender(
        <QueryClientProvider client={view.client}>
          <NewsDetailEditDialog {...makeProps({ newsId: "news-next", initialData: replacement })} />
        </QueryClientProvider>
      )

      expect(await screen.findByDisplayValue(replacement.title)).toHaveValue(replacement.title)
      expect(screen.getByDisplayValue(replacement.content)).toHaveValue(replacement.content)
      expect(screen.queryByDisplayValue("Previous item draft title")).not.toBeInTheDocument()
      expect(screen.queryByDisplayValue("Previous item draft content")).not.toBeInTheDocument()

      await user.click(screen.getByRole("button", { name: "common:buttons.save" }))
      await waitFor(() => expect(apiMocks.updateNews).toHaveBeenCalledOnce())
      expect(apiMocks.updateNews).toHaveBeenCalledWith("news-next", replacement)
    } finally {
      view.unmount()
      view.client.clear()
    }
  })

  it("preserves a dirty English draft through a same-item refresh", async () => {
    const source = {
      ...initialData,
      title: "Russian source title",
      content: "Russian source content",
    }
    apiMocks.fetchNewsItem.mockResolvedValue({ status: 200, data: source })
    const view = renderDialog({ language: "en" })

    try {
      await screen.findByDisplayValue(source.title)
      fireEvent.change(screen.getByDisplayValue(source.title_en), {
        target: { value: "Unsaved English translation" },
      })
      view.rerender(
        <QueryClientProvider client={view.client}>
          <NewsDetailEditDialog
            {...makeProps({
              language: "en",
              initialData: {
                ...initialData,
                title: "Refreshed localized title",
                title_en: "Refreshed translation",
              },
            })}
          />
        </QueryClientProvider>
      )

      expect(screen.getByDisplayValue("Unsaved English translation")).toBeInTheDocument()
      expect(screen.getByDisplayValue(source.title)).toBeInTheDocument()
      expect(screen.queryByRole("status")).not.toBeInTheDocument()
      expect(apiMocks.fetchNewsItem).toHaveBeenCalledOnce()

      fireEvent.click(screen.getByRole("button", { name: "common:buttons.save" }))
      await waitFor(() => expect(apiMocks.updateNews).toHaveBeenCalledOnce())
      expect(apiMocks.updateNews).toHaveBeenCalledWith("news-contract", {
        ...source,
        title_en: "Unsaved English translation",
      })
      await waitFor(() =>
        expect(screen.getByRole("button", { name: "common:buttons.save" })).toBeEnabled()
      )
    } finally {
      view.unmount()
      view.client.clear()
    }
  })

  it("preserves an image-only draft through a same-item refresh", async () => {
    const create = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:image-only-draft")
    const revoke = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined)
    const view = renderDialog()

    try {
      const file = new File(["draft"], "draft.png", { type: "image/png" })
      const input = document.querySelector<HTMLInputElement>('input[type="file"]')!
      fireEvent.change(input, { target: { files: [file] } })
      expect(create).toHaveBeenCalledWith(file)
      view.rerender(
        <QueryClientProvider client={view.client}>
          <NewsDetailEditDialog
            {...makeProps({
              initialData: {
                ...initialData,
                title: "Refreshed image-only title",
                image_url: "https://example.test/refreshed.png",
              },
            })}
          />
        </QueryClientProvider>
      )

      expect(screen.getByTestId("edit-preview")).toHaveAttribute("src", "blob:image-only-draft")
      expect(screen.getByDisplayValue(initialData.title)).toBeInTheDocument()
      expect(revoke).not.toHaveBeenCalled()

      fireEvent.click(screen.getByRole("button", { name: "common:buttons.save" }))
      await waitFor(() => expect(apiMocks.updateNews).toHaveBeenCalledOnce())
      expect(apiMocks.uploadNewsImage).toHaveBeenCalledExactlyOnceWith(file)
      expect(apiMocks.updateNews).toHaveBeenCalledWith("news-contract", {
        ...initialData,
        image_url: "https://example.test/uploaded.png",
      })
      await waitFor(() =>
        expect(screen.getByRole("button", { name: "common:buttons.save" })).toBeEnabled()
      )
    } finally {
      view.unmount()
      view.client.clear()
      create.mockRestore()
      revoke.mockRestore()
    }
  })

  it.each(["new-item", "language", "close-reopen"] as const)(
    "clears a selected image across the %s session boundary",
    async (boundary) => {
      const create = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:previous-session")
      const revoke = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined)
      const view = renderDialog()
      const replacement = {
        ...initialData,
        title: "Replacement session title",
        content: "Replacement session content",
        image_url: "https://example.test/replacement-session.png",
      }

      try {
        const file = new File(["previous"], "previous.png", { type: "image/png" })
        const input = document.querySelector<HTMLInputElement>('input[type="file"]')!
        fireEvent.change(input, { target: { files: [file] } })
        expect(screen.getByTestId("edit-preview")).toHaveAttribute("src", "blob:previous-session")

        const newsId = boundary === "new-item" ? "news-next" : "news-contract"
        const language = boundary === "language" ? "en" : "ru"
        apiMocks.fetchNewsItem.mockResolvedValue({ status: 200, data: replacement })

        if (boundary === "close-reopen") {
          // Exercise an external close, not handleClose's existing cleanup.
          view.rerender(
            <QueryClientProvider client={view.client}>
              <NewsDetailEditDialog {...makeProps({ open: false })} />
            </QueryClientProvider>
          )
        }

        view.rerender(
          <QueryClientProvider client={view.client}>
            <NewsDetailEditDialog {...makeProps({ newsId, language, initialData: replacement })} />
          </QueryClientProvider>
        )

        await screen.findByDisplayValue(replacement.title)
        expect(screen.getByTestId("edit-preview")).toHaveAttribute("src", replacement.image_url)
        expect(screen.getByText("common:buttons.uploadPhoto")).toBeInTheDocument()
        expect(
          screen.queryByRole("button", { name: "common:buttons.reset" })
        ).not.toBeInTheDocument()
        expect(revoke).toHaveBeenCalledExactlyOnceWith("blob:previous-session")
        expect(document.querySelector<HTMLInputElement>('input[type="file"]')).toHaveValue("")

        if (boundary === "language") {
          expect(apiMocks.fetchNewsItem).toHaveBeenCalledExactlyOnceWith(
            newsId,
            expect.objectContaining({ language: "ru", signal: expect.any(AbortSignal) })
          )
        } else {
          expect(apiMocks.fetchNewsItem).not.toHaveBeenCalled()
        }

        fireEvent.click(screen.getByRole("button", { name: "common:buttons.save" }))
        await waitFor(() => expect(apiMocks.updateNews).toHaveBeenCalledOnce())
        expect(apiMocks.updateNews).toHaveBeenCalledWith(newsId, replacement)
        expect(apiMocks.uploadNewsImage).not.toHaveBeenCalled()
        await waitFor(() =>
          expect(screen.getByRole("button", { name: "common:buttons.save" })).toBeEnabled()
        )
      } finally {
        view.unmount()
        view.client.clear()
        create.mockRestore()
        revoke.mockRestore()
      }
    }
  )

  it("aborts a pristine English source request when same-item data refreshes", async () => {
    const requests: Array<{
      signal: AbortSignal
      resolve: (value: { status: number; data: typeof initialData }) => void
    }> = []
    apiMocks.fetchNewsItem.mockImplementation(
      (_newsId: string, options: { signal: AbortSignal }) =>
        new Promise<{ status: number; data: typeof initialData }>((resolve) => {
          requests.push({ signal: options.signal, resolve })
        })
    )
    const view = renderDialog({ language: "en" })

    try {
      expect(requests).toHaveLength(1)
      view.rerender(
        <QueryClientProvider client={view.client}>
          <NewsDetailEditDialog
            {...makeProps({
              language: "en",
              initialData: { ...initialData, title: "Refreshed localized display" },
            })}
          />
        </QueryClientProvider>
      )

      expect(requests).toHaveLength(2)
      expect(requests[0]!.signal.aborted).toBe(true)
      expect(requests[1]!.signal.aborted).toBe(false)
      expect(apiMocks.fetchNewsItem).toHaveBeenNthCalledWith(
        2,
        "news-contract",
        expect.objectContaining({ language: "ru", signal: requests[1]!.signal })
      )

      await act(async () => {
        requests[0]!.resolve({
          status: 200,
          data: { ...initialData, title: "Stale pending source" },
        })
      })
      expect(screen.queryByDisplayValue("Stale pending source")).not.toBeInTheDocument()
      expect(screen.getByRole("status")).toHaveTextContent("common:statuses.loading")
      expect(screen.getByRole("button", { name: "common:buttons.save" })).toBeDisabled()

      const current = {
        ...initialData,
        title: "Current refreshed source",
        content: "Current refreshed source content",
      }
      await act(async () => {
        requests[1]!.resolve({ status: 200, data: current })
      })
      await screen.findByDisplayValue(current.title)
      expect(screen.queryByDisplayValue("Stale pending source")).not.toBeInTheDocument()

      fireEvent.click(screen.getByRole("button", { name: "common:buttons.save" }))
      await waitFor(() => expect(apiMocks.updateNews).toHaveBeenCalledOnce())
      expect(apiMocks.updateNews).toHaveBeenCalledWith("news-contract", current)
      expect(apiMocks.fetchNewsItem).toHaveBeenCalledTimes(2)
      await waitFor(() =>
        expect(screen.getByRole("button", { name: "common:buttons.save" })).toBeEnabled()
      )
    } finally {
      view.unmount()
      view.client.clear()
    }
  })
})
