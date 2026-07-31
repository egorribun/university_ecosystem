import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, it, expect, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
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

  it("renders the dialog with prefilled fields when open", () => {
    render(<NewsCardEditDialog {...baseProps} />)
    expect(screen.getByText("news:dialogs.edit.title")).toBeInTheDocument()
    expect(screen.getByDisplayValue(initialData.title)).toBeInTheDocument()
    expect(screen.getByDisplayValue(initialData.content)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "common:buttons.save" })).toBeInTheDocument()
  })

  it("does not render the dialog body when closed", () => {
    render(<NewsCardEditDialog {...baseProps} open={false} />)
    expect(screen.queryByText("news:dialogs.edit.title")).not.toBeInTheDocument()
  })

  it("renders the form without an image preview when no image is available", () => {
    render(<NewsCardEditDialog {...baseProps} initialData={{ ...initialData, image_url: "" }} />)

    expect(screen.queryByRole("img")).not.toBeInTheDocument()
  })

  it("fires onClose from the cancel button", async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<NewsCardEditDialog {...baseProps} onClose={onClose} />)
    await user.click(screen.getByRole("button", { name: "common:buttons.cancel" }))
    expect(onClose).toHaveBeenCalledOnce()
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
    expect(onSuccess).not.toHaveBeenCalled()
    expect(onClose).not.toHaveBeenCalled()
  })
})
