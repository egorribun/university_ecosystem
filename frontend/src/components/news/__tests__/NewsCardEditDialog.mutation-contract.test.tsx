import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ComponentProps } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const translationMocks = vi.hoisted(() => ({
  returnUndefined: false,
  namespaceCalls: [] as unknown[],
}))

const apiMocks = vi.hoisted(() => ({
  post: vi.fn(),
  patch: vi.fn(),
  logError: vi.fn(),
}))

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: (namespaces: unknown) => {
    translationMocks.namespaceCalls.push(namespaces)
    return {
      t: (key: string) => (translationMocks.returnUndefined ? undefined : key),
      i18n: { language: "en", changeLanguage: () => Promise.resolve() },
    }
  },
}))

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>()
  return {
    ...actual,
    default: {
      ...actual.default,
      post: apiMocks.post,
      patch: apiMocks.patch,
    },
  }
})
vi.mock("@/app/logger", () => ({ logError: apiMocks.logError }))

import { NewsCardEditDialog, type NewsEditData } from "@/components/news/NewsCardEditDialog"

const makeData = (overrides: Partial<NewsEditData> = {}): NewsEditData => ({
  title: "Открыт набор в студенческий совет",
  content: "Подавайте заявки до конца месяца.",
  title_en: "Student council applications are open",
  content_en: "Apply by the end of the month.",
  image_url: "https://picsum.photos/seed/news-edit/640/360",
  ...overrides,
})

const makeProps = (overrides: Partial<ComponentProps<typeof NewsCardEditDialog>> = {}) => ({
  id: "news-contract",
  open: true,
  onClose: vi.fn(),
  initialData: makeData(),
  onSuccess: vi.fn(),
  ...overrides,
})

describe("NewsCardEditDialog mutation contracts", () => {
  beforeEach(() => {
    translationMocks.returnUndefined = false
    translationMocks.namespaceCalls = []
    apiMocks.post.mockReset()
    apiMocks.patch.mockReset().mockResolvedValue({ data: {} })
    apiMocks.logError.mockReset()
  })

  it("keeps the namespace, accessibility, field, and class contracts exact", () => {
    const props = makeProps()
    render(<NewsCardEditDialog {...props} />)

    expect(translationMocks.namespaceCalls).toContainEqual(["news", "common"])

    const dialog = screen.getByRole("dialog")
    expect(dialog).toHaveAttribute("aria-modal", "true")
    expect(dialog).toHaveClass("sm:max-w-[32rem]", "h-dvh", "sm:h-auto")
    expect(screen.getByRole("heading", { name: "news:dialogs.edit.title" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "common:buttons.close" })).toBeInTheDocument()

    const form = document.getElementById("news-edit-form-news-contract")
    expect(form).toBeInTheDocument()
    expect(form).toHaveClass("space-y-4")

    const title = screen.getByLabelText(/^news:form\.title\*/)
    const content = screen.getByLabelText(/^news:form\.text\*/)
    const titleEn = screen.getByLabelText("news:form.title_en")
    const contentEn = screen.getByLabelText("news:form.content_en")
    expect(title).toHaveAttribute("id", "news-edit-title-news-contract")
    expect(content).toHaveAttribute("id", "news-edit-content-news-contract")
    expect(titleEn).toHaveAttribute("id", "news-edit-title-en-news-contract")
    expect(contentEn).toHaveAttribute("id", "news-edit-content-en-news-contract")
    expect(title).toHaveClass(
      "w-full",
      "rounded-xl",
      "border-glass-border",
      "bg-input-mix",
      "shadow-inner-premium",
      "focus-ring-premium"
    )
    expect(content).toHaveClass("min-h-(--space-32)", "resize-y", "leading-relaxed")
    expect(screen.getByRole("button", { name: "common:buttons.save" })).toHaveAttribute(
      "form",
      "news-edit-form-news-contract"
    )

    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!
    expect(fileInput).toHaveAttribute("accept", "image/*")
    expect(fileInput).toHaveAttribute("type", "file")
    expect(fileInput).toHaveValue("")
    expect(fileInput).toHaveAttribute("hidden")

    const image = screen.getByRole("img", { name: "news:alt.preview" })
    expect(image).toHaveClass("h-20", "max-w-44", "rounded-lg", "object-cover", "shadow-surface")
    expect(screen.getByRole("button", { name: "common:buttons.cancel" })).toHaveClass(
      "w-full",
      "sm:w-auto"
    )
  })

  it("resets all values for new data while open and normalizes optional translations", async () => {
    const props = makeProps()
    const view = render(<NewsCardEditDialog {...props} />)
    const user = userEvent.setup()
    const title = screen.getByLabelText(/^news:form\.title\*/)
    await user.clear(title)
    await user.type(title, "edited before rerender")

    view.rerender(
      <NewsCardEditDialog
        {...props}
        initialData={makeData({
          title: "Replacement title",
          content: "Replacement body",
          title_en: "",
          content_en: "",
          image_url: "",
        })}
      />
    )

    await waitFor(() => {
      expect(screen.getByDisplayValue("Replacement title")).toBeInTheDocument()
      expect(screen.getByDisplayValue("Replacement body")).toBeInTheDocument()
    })
    expect(screen.getByLabelText("news:form.title_en")).toHaveValue("")
    expect(screen.getByLabelText("news:form.content_en")).toHaveValue("")
    expect(screen.queryByRole("img")).not.toBeInTheDocument()
  })

  it("prefers the selected preview and ignores empty or null file selections", async () => {
    const createObjectURL = vi
      .spyOn(URL, "createObjectURL")
      .mockReturnValue("blob:contract-preview")
    const revokeObjectURL = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined)
    const view = render(<NewsCardEditDialog {...makeProps()} />)
    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!
    const file = new File(["image"], "cover.png", { type: "image/png" })

    fireEvent.change(fileInput, { target: { files: [file] } })
    await waitFor(() => expect(createObjectURL).toHaveBeenCalledWith(file))
    expect(screen.getByRole("img", { name: "news:alt.preview" })).toHaveAttribute(
      "src",
      "blob:contract-preview"
    )

    fireEvent.change(fileInput, { target: { files: [] } })
    expect(screen.getByRole("img", { name: "news:alt.preview" })).toHaveAttribute(
      "src",
      "blob:contract-preview"
    )

    Object.defineProperty(fileInput, "files", { configurable: true, value: null })
    expect(() => fireEvent.change(fileInput)).not.toThrow()
    expect(screen.getByRole("img", { name: "news:alt.preview" })).toHaveAttribute(
      "src",
      "blob:contract-preview"
    )

    view.unmount()
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:contract-preview")
    createObjectURL.mockRestore()
    revokeObjectURL.mockRestore()
  })

  it("marks every invalid field and the image control without adding error styles to valid fields", async () => {
    const user = userEvent.setup()
    render(<NewsCardEditDialog {...makeProps()} />)

    const title = screen.getByLabelText(/^news:form\.title\*/)
    const content = screen.getByLabelText(/^news:form\.text\*/)
    const titleEn = screen.getByLabelText("news:form.title_en")
    const contentEn = screen.getByLabelText("news:form.content_en")
    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!
    const photoButton = screen.getByText("news:form.changePhoto").closest("label")!

    expect(title).not.toHaveClass("border-error-text/50")
    expect(content).not.toHaveClass("border-error-text/50")
    expect(titleEn).not.toHaveClass("border-error-text/50")
    expect(contentEn).not.toHaveClass("border-error-text/50")
    expect(photoButton).toHaveClass("w-full", "sm:w-auto")
    expect(photoButton).not.toHaveClass("border-error-text/50", "text-error-text")

    await user.clear(title)
    await user.tab()
    await user.clear(content)
    await user.tab()
    fireEvent.change(titleEn, { target: { value: "x".repeat(101) } })
    fireEvent.blur(titleEn)
    fireEvent.change(contentEn, { target: { value: "x".repeat(3001) } })
    fireEvent.blur(contentEn)
    fireEvent.change(fileInput, {
      target: { files: [new File(["not-image"], "notes.txt", { type: "text/plain" })] },
    })

    await waitFor(() => {
      expect(screen.getByText("Title is required")).toBeInTheDocument()
      expect(screen.getByText("Content is required")).toBeInTheDocument()
      expect(screen.getByText("Title (EN) must be less than 100 characters")).toBeInTheDocument()
      expect(screen.getByText("Content (EN) must be less than 3000 characters")).toBeInTheDocument()
      expect(
        screen.getByText("Only .jpg, .jpeg, .png and .webp formats are supported.")
      ).toBeInTheDocument()
    })

    expect(title).toHaveClass("border-error-text/50")
    expect(content).toHaveClass("border-error-text/50")
    expect(titleEn).toHaveClass("border-error-text/50")
    expect(contentEn).toHaveClass("border-error-text/50")
    expect(photoButton).toHaveClass("border-error-text/50", "text-error-text")
    expect(screen.getByText("Title is required")).toHaveClass(
      "text-error-text",
      "text-xs",
      "mt-1",
      "font-medium"
    )
    expect(screen.getByRole("button", { name: "common:buttons.save" })).toBeDisabled()
  })

  it("keeps upload and submit controls disabled/loading and sends the selected file", async () => {
    const user = userEvent.setup()
    let resolveUpload: (value: { data: { url: string } }) => void = () => undefined
    let resolvePatch: (value: { data: Record<string, never> }) => void = () => undefined
    apiMocks.post.mockImplementation(
      () =>
        new Promise<{ data: { url: string } }>((resolve) => {
          resolveUpload = resolve
        })
    )
    apiMocks.patch.mockImplementation(
      () =>
        new Promise<{ data: Record<string, never> }>((resolve) => {
          resolvePatch = resolve
        })
    )
    render(<NewsCardEditDialog {...makeProps()} />)

    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!
    const photoButton = screen.getByText("news:form.changePhoto").closest("label")!
    const cancelButton = screen.getByRole("button", { name: "common:buttons.cancel" })
    const saveButton = screen.getByRole("button", { name: "common:buttons.save" })
    const file = new File(["image"], "cover.png", { type: "image/png" })
    expect(photoButton).not.toHaveAttribute("aria-disabled", "true")

    fireEvent.change(fileInput, { target: { files: [file] } })
    await user.click(saveButton)

    await waitFor(() => expect(screen.getByText("common:statuses.uploading")).toBeInTheDocument())
    expect(screen.getByText("common:statuses.uploading").closest("label")).toHaveAttribute(
      "aria-disabled",
      "true"
    )
    expect(cancelButton).toBeDisabled()
    expect(saveButton).toBeDisabled()
    expect(saveButton).toHaveAttribute("aria-busy", "true")

    resolveUpload({ data: { url: "https://example.test/uploaded.png" } })
    await waitFor(() => expect(apiMocks.patch).toHaveBeenCalled())

    const uploadCall = apiMocks.post.mock.calls[0]!
    expect(uploadCall[0]).toBe("/news/upload_image")
    expect(uploadCall[1]).toBeInstanceOf(FormData)
    expect((uploadCall[1] as FormData).get("file")).toBe(file)
    expect(screen.getByText("news:form.changePhoto").closest("label")).toHaveAttribute(
      "aria-disabled",
      "true"
    )
    expect(cancelButton).toBeDisabled()
    expect(saveButton).toBeDisabled()
    expect(saveButton).toHaveAttribute("aria-busy", "true")

    resolvePatch({ data: {} })
    await waitFor(() => expect(apiMocks.patch).toHaveBeenCalledTimes(1))
  })

  it("renders empty translation fallbacks instead of leaking mutation text", () => {
    translationMocks.returnUndefined = true
    render(<NewsCardEditDialog {...makeProps()} />)

    const requiredTitleLabel = document.querySelector<HTMLLabelElement>(
      'label[for="news-edit-title-news-contract"]'
    )!
    const requiredContentLabel = document.querySelector<HTMLLabelElement>(
      'label[for="news-edit-content-news-contract"]'
    )!
    const optionalTitleLabel = document.querySelector<HTMLLabelElement>(
      'label[for="news-edit-title-en-news-contract"]'
    )!
    const optionalContentLabel = document.querySelector<HTMLLabelElement>(
      'label[for="news-edit-content-en-news-contract"]'
    )!
    expect(requiredTitleLabel.textContent?.trim()).toBe("*")
    expect(requiredContentLabel.textContent?.trim()).toBe("*")
    expect(optionalTitleLabel.textContent?.trim()).toBe("")
    expect(optionalContentLabel.textContent?.trim()).toBe("")
    expect(screen.getByRole("dialog")).toHaveAttribute("aria-label", "Close")
  })
})
