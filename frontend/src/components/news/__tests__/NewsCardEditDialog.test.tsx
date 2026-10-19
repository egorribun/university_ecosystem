import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, it, expect, vi } from "vitest"

const translationMocks = vi.hoisted(() => ({
  returnUndefined: false,
}))

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => (translationMocks.returnUndefined ? undefined : key),
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

const apiMocks = vi.hoisted(() => ({
  post: vi.fn(),
  patch: vi.fn(),
  logError: vi.fn(),
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

const initialData: NewsEditData = {
  title: "Открыт набор в студенческий совет",
  content: "Подавайте заявки до конца месяца.",
  title_en: "Student council applications are open",
  content_en: "Apply by the end of the month.",
  image_url: "https://picsum.photos/seed/news-edit/640/360",
}

const baseProps = {
  id: "news-1",
  open: true,
  onClose: vi.fn(),
  initialData,
  onSuccess: vi.fn(),
}

describe("NewsCardEditDialog", () => {
  beforeEach(() => {
    apiMocks.post.mockReset()
    apiMocks.patch.mockReset().mockResolvedValue({ data: {} })
    apiMocks.logError.mockReset()
  })

  it("renders the dialog with prefilled fields when open", async () => {
    await act(async () => {
      render(<NewsCardEditDialog {...baseProps} />)
    })
    expect(screen.getByText("news:dialogs.edit.title")).toBeInTheDocument()
    expect(screen.getByDisplayValue(initialData.title)).toBeInTheDocument()
    expect(screen.getByDisplayValue(initialData.content)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "common:buttons.save" })).toBeInTheDocument()
  })

  it("provides an accessible description for the edit dialog", async () => {
    await act(async () => {
      render(<NewsCardEditDialog {...baseProps} />)
    })

    const dialog = screen.getByRole("dialog")
    const descriptionId = dialog.getAttribute("aria-describedby")
    expect(descriptionId).toBeTruthy()
    expect(document.getElementById(descriptionId!)).toHaveTextContent(
      "news:dialogs.edit.description"
    )
  })

  it("does not render the dialog body when closed", async () => {
    await act(async () => {
      render(<NewsCardEditDialog {...baseProps} open={false} />)
    })
    expect(screen.queryByText("news:dialogs.edit.title")).not.toBeInTheDocument()
  })

  it("renders the form without an image preview when no image is available", async () => {
    await act(async () => {
      render(<NewsCardEditDialog {...baseProps} initialData={{ ...initialData, image_url: "" }} />)
    })

    expect(screen.queryByRole("img")).not.toBeInTheDocument()
  })

  it("sends cleared English translations as null so the server clears them", async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(
      <NewsCardEditDialog
        {...baseProps}
        onClose={onClose}
        onSuccess={undefined}
        initialData={{ ...initialData, title_en: "", content_en: "", image_url: "" }}
      />
    )

    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))

    await waitFor(() => {
      expect(apiMocks.patch).toHaveBeenCalledWith("/news/news-1", {
        title: initialData.title,
        content: initialData.content,
        title_en: null,
        content_en: null,
        image_url: "",
      })
    })
    expect(onClose).toHaveBeenCalledOnce()
  })

  it("keeps a filled English translation in the save payload", async () => {
    const user = userEvent.setup()
    render(
      <NewsCardEditDialog
        {...baseProps}
        initialData={{ ...initialData, title_en: "English title", content_en: "English body" }}
      />
    )

    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))

    await waitFor(() => {
      expect(apiMocks.patch).toHaveBeenCalledWith(
        "/news/news-1",
        expect.objectContaining({ title_en: "English title", content_en: "English body" })
      )
    })
  })

  it("closes a clean edit directly without opening discard confirmation", async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<NewsCardEditDialog {...baseProps} onClose={onClose} />)

    await user.click(screen.getByRole("button", { name: "common:buttons.cancel" }))

    expect(onClose).toHaveBeenCalledOnce()
    expect(screen.queryByText("common:dialogs.unsavedChanges.description")).not.toBeInTheDocument()
  })

  it("confirms before discarding edited news from Cancel, Escape, or the backdrop", async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<NewsCardEditDialog {...baseProps} onClose={onClose} />)
    const title = screen.getByLabelText(/^news:form\.title\*/)
    await user.type(title, " updated")

    await user.keyboard("{Escape}")
    expect(screen.getByText("common:dialogs.unsavedChanges.description")).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
    await user.click(screen.getByRole("button", { name: "common:buttons.keepEditing" }))
    expect(screen.getByLabelText(/^news:form\.title\*/)).toHaveValue(`${initialData.title} updated`)

    const backdrop = document.querySelector('[role="presentation"] > div[aria-hidden="true"]')
    if (!(backdrop instanceof HTMLElement)) throw new Error("Dialog backdrop not found")
    fireEvent.click(backdrop)
    expect(screen.getByText("common:dialogs.unsavedChanges.description")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "common:buttons.keepEditing" }))

    await user.click(screen.getByRole("button", { name: "common:buttons.cancel" }))
    expect(screen.getByText("common:dialogs.unsavedChanges.description")).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
    await user.click(screen.getByRole("button", { name: "common:buttons.discardChanges" }))

    expect(onClose).toHaveBeenCalledOnce()
    expect(screen.getByDisplayValue(initialData.title)).toBeInTheDocument()
  })

  it("restores empty optional translations when discarding a dirty edit", async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    const emptyTranslations = { ...initialData, title_en: "", content_en: "" }
    render(<NewsCardEditDialog {...baseProps} initialData={emptyTranslations} onClose={onClose} />)

    await user.type(screen.getByLabelText(/^news:form\.title\*/), " updated")
    await user.click(screen.getByRole("button", { name: "common:buttons.cancel" }))
    expect(screen.getByText("common:dialogs.unsavedChanges.description")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "common:buttons.discardChanges" }))

    expect(onClose).toHaveBeenCalledOnce()
    expect(screen.getByLabelText("news:form.title_en")).toHaveValue("")
    expect(screen.getByLabelText("news:form.content_en")).toHaveValue("")
    expect(screen.getByLabelText(/^news:form\.title\*/)).toHaveValue(emptyTranslations.title)
  })

  it("shows validation feedback and keeps save disabled for empty required fields", async () => {
    const user = userEvent.setup()
    render(
      <NewsCardEditDialog {...baseProps} initialData={{ ...initialData, title: "", content: "" }} />
    )

    const title = screen.getByLabelText(/^news:form\.title\*/)
    await user.type(title, "x")
    await user.clear(title)
    await user.tab()

    await waitFor(() => {
      expect(screen.getByText("Title is required")).toBeInTheDocument()
    })
    expect(screen.getByRole("button", { name: "common:buttons.save" })).toBeDisabled()
  })

  it("renders content and English-field validation states", async () => {
    const user = userEvent.setup()
    render(
      <NewsCardEditDialog
        {...baseProps}
        initialData={{ ...initialData, title: "", content: "", title_en: "", content_en: "" }}
      />
    )

    const content = screen.getByLabelText(/^news:form\.text\*/)
    await user.type(content, "x")
    await user.clear(content)
    await user.tab()

    await waitFor(() => expect(screen.getByText("Content is required")).toBeInTheDocument())

    const titleEn = screen.getByLabelText("news:form.title_en")
    fireEvent.change(titleEn, { target: { value: "x".repeat(101) } })
    fireEvent.blur(titleEn)

    const contentEn = screen.getByLabelText("news:form.content_en")
    fireEvent.change(contentEn, { target: { value: "x".repeat(3001) } })
    fireEvent.blur(contentEn)

    await waitFor(() => {
      expect(screen.getByText("Title (EN) must be less than 100 characters")).toBeInTheDocument()
      expect(screen.getByText("Content (EN) must be less than 3000 characters")).toBeInTheDocument()
    })
  })

  it("submits the edited fields and closes after a successful update", async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    const onSuccess = vi.fn()
    render(<NewsCardEditDialog {...baseProps} onClose={onClose} onSuccess={onSuccess} />)

    const title = screen.getByLabelText(/^news:form\.title\*/)
    await user.clear(title)
    await user.type(title, "Updated title")
    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))

    await waitFor(() => {
      expect(apiMocks.patch).toHaveBeenCalledWith("/news/news-1", {
        title: "Updated title",
        content: initialData.content,
        title_en: initialData.title_en,
        content_en: initialData.content_en,
        image_url: initialData.image_url,
      })
    })
    expect(onSuccess).toHaveBeenCalledOnce()
    expect(onClose).toHaveBeenCalledOnce()
  })

  it("uploads a selected image, previews it, and revokes the previous preview", async () => {
    const user = userEvent.setup()
    const firstFile = new File(["first"], "first.png", { type: "image/png" })
    const secondFile = new File(["second"], "second.png", { type: "image/png" })
    const createObjectURL = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:first")
    const revokeObjectURL = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined)
    apiMocks.post.mockResolvedValue({ data: { url: "https://example.test/new-image.png" } })

    render(<NewsCardEditDialog {...baseProps} />)

    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')
    expect(fileInput).not.toBeNull()
    fireEvent.change(fileInput as HTMLInputElement, { target: { files: [firstFile] } })
    await waitFor(() => expect(createObjectURL).toHaveBeenCalledWith(firstFile))

    createObjectURL.mockReturnValue("blob:second")
    fireEvent.change(fileInput as HTMLInputElement, { target: { files: [secondFile] } })
    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith("blob:first"))

    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))
    await waitFor(() => {
      expect(apiMocks.post).toHaveBeenCalledWith(
        "/news/upload_image",
        expect.any(FormData),
        expect.objectContaining({ headers: { "Content-Type": "multipart/form-data" } })
      )
      expect(apiMocks.patch).toHaveBeenCalledWith(
        "/news/news-1",
        expect.objectContaining({ image_url: "https://example.test/new-image.png" })
      )
    })

    createObjectURL.mockRestore()
    revokeObjectURL.mockRestore()
  })

  it("ignores an image input change without a selected file", async () => {
    await act(async () => {
      render(<NewsCardEditDialog {...baseProps} />)
    })
    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')!

    fireEvent.change(fileInput, { target: { files: [] } })

    expect(apiMocks.post).not.toHaveBeenCalled()
  })

  it("shows the uploading state while an image upload is pending", async () => {
    const user = userEvent.setup()
    let resolveUpload: (value: { data: { url: string } }) => void = () => undefined
    apiMocks.post.mockImplementation(
      () =>
        new Promise<{ data: { url: string } }>((resolve) => {
          resolveUpload = resolve
        })
    )
    render(<NewsCardEditDialog {...baseProps} />)

    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')
    fireEvent.change(fileInput as HTMLInputElement, {
      target: { files: [new File(["image"], "image.png", { type: "image/png" })] },
    })
    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))

    await waitFor(() => expect(screen.getByText("common:statuses.uploading")).toBeInTheDocument())
    expect(screen.getByRole("button", { name: "common:buttons.save" })).toBeDisabled()

    resolveUpload({ data: { url: "https://example.test/uploaded.png" } })
    await waitFor(() => expect(apiMocks.patch).toHaveBeenCalled())
  })

  it("shows the image validation error for an unsupported file type", async () => {
    const user = userEvent.setup()
    render(<NewsCardEditDialog {...baseProps} />)

    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')
    fireEvent.change(fileInput as HTMLInputElement, {
      target: { files: [new File(["not-an-image"], "notes.txt", { type: "text/plain" })] },
    })

    await waitFor(() => {
      expect(
        screen.getByText("Only .jpg, .jpeg, .png and .webp formats are supported.")
      ).toBeInTheDocument()
    })
    expect(screen.getByRole("button", { name: "common:buttons.save" })).toBeDisabled()
    await user.click(screen.getByRole("button", { name: "common:buttons.cancel" }))
  })

  it("logs API failures and still clears image-loading state after upload failure", async () => {
    const user = userEvent.setup()
    const uploadError = new Error("upload failed")
    apiMocks.post.mockRejectedValueOnce(uploadError)
    render(<NewsCardEditDialog {...baseProps} />)

    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')
    fireEvent.change(fileInput as HTMLInputElement, {
      target: { files: [new File(["image"], "image.png", { type: "image/png" })] },
    })
    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))

    await waitFor(() => expect(apiMocks.logError).toHaveBeenCalledWith(uploadError))
    expect(apiMocks.patch).not.toHaveBeenCalled()
    expect(screen.getByRole("alert")).toHaveTextContent("news:form.errors.uploadFailed")
    expect(screen.getByText("news:form.changePhoto")).toBeInTheDocument()
  })

  it("logs patch failures without calling success or close callbacks", async () => {
    const user = userEvent.setup()
    const patchError = new Error("patch failed")
    const onClose = vi.fn()
    const onSuccess = vi.fn()
    apiMocks.patch.mockRejectedValueOnce(patchError)
    render(<NewsCardEditDialog {...baseProps} onClose={onClose} onSuccess={onSuccess} />)

    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))

    await waitFor(() => expect(apiMocks.logError).toHaveBeenCalledWith(patchError))
    expect(screen.getByRole("alert")).toHaveTextContent("news:notifications.savedError")
    expect(onSuccess).not.toHaveBeenCalled()
    expect(onClose).not.toHaveBeenCalled()
  })

  it("logs a post-save callback exception without losing the open editor", async () => {
    const user = userEvent.setup()
    const callbackError = new Error("refresh callback failed")
    const onClose = vi.fn()
    const onSuccess = vi.fn(() => {
      throw callbackError
    })
    render(<NewsCardEditDialog {...baseProps} onClose={onClose} onSuccess={onSuccess} />)

    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))

    await waitFor(() => {
      expect(apiMocks.patch).toHaveBeenCalledOnce()
      expect(apiMocks.logError).toHaveBeenCalledWith(callbackError)
    })
    expect(onSuccess).toHaveBeenCalledOnce()
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })

  it("keeps the dialog and draft while a save is pending", async () => {
    const user = userEvent.setup()
    let resolvePatch: (value: { data: Record<string, never> }) => void = () => undefined
    apiMocks.patch.mockImplementationOnce(
      () =>
        new Promise<{ data: Record<string, never> }>((resolve) => {
          resolvePatch = resolve
        })
    )
    const onClose = vi.fn()
    render(<NewsCardEditDialog {...baseProps} onClose={onClose} />)

    const title = screen.getByLabelText(/^news:form\.title\*/)
    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))
    await waitFor(() => expect(apiMocks.patch).toHaveBeenCalledOnce())
    expect(title).toBeDisabled()

    await user.keyboard("{Escape}")
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()

    await act(async () => {
      resolvePatch({ data: {} })
    })
    await waitFor(() => expect(onClose).toHaveBeenCalledOnce())
  })

  it("falls back to empty labels when translations are unavailable", async () => {
    translationMocks.returnUndefined = true
    try {
      let view: ReturnType<typeof render> | undefined
      await act(async () => {
        view = render(<NewsCardEditDialog {...baseProps} />)
      })
      expect(screen.getByRole("dialog")).toBeInTheDocument()
      if (!view) throw new Error("Dialog failed to render")
      view.unmount()
    } finally {
      translationMocks.returnUndefined = false
    }
  })

  it("sends null after clearing populated English translations", async () => {
    const user = userEvent.setup()
    render(<NewsCardEditDialog {...baseProps} />)
    const titleEn = screen.getByLabelText("news:form.title_en")
    const contentEn = screen.getByLabelText("news:form.content_en")
    expect(titleEn).toHaveValue(initialData.title_en)
    expect(contentEn).toHaveValue(initialData.content_en)

    await user.clear(titleEn)
    await user.clear(contentEn)
    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))

    await waitFor(() => {
      expect(apiMocks.patch).toHaveBeenCalledWith("/news/news-1", {
        title: initialData.title,
        content: initialData.content,
        title_en: null,
        content_en: null,
        image_url: initialData.image_url,
      })
    })
    expect(apiMocks.patch).toHaveBeenCalledOnce()
  })
})
