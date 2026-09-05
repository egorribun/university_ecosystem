import { fireEvent, render, screen, waitFor } from "@testing-library/react"
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
  updateNews: apiMocks.updateNews,
  uploadNewsImage: apiMocks.uploadNewsImage,
}))
vi.mock("@/components/media/SmartImage", () => ({
  default: ({ srcRaw, alt, className }: { srcRaw?: string; alt?: string; className?: string }) => (
    <img data-testid="edit-preview" src={srcRaw} alt={alt} className={className} />
  ),
}))

import { NewsDetailEditDialog } from "@/components/news/NewsDetailEditDialog"

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
})
