import { beforeEach, describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import StoriesAdmin from "../StoriesAdmin"

const mocks = vi.hoisted(() => ({
  user: { id: "admin-1", role: "admin" as "admin" | "student" },
  getStories: vi.fn(),
  createStory: vi.fn(),
  deleteStory: vi.fn(),
  updateStory: vi.fn(),
  uploadStoryCover: vi.fn(),
  t: (key: string) => key,
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: mocks.t }),
}))

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: mocks.user }),
}))

vi.mock("@/api/client", () => ({
  default: { get: mocks.getStories },
}))

vi.mock("@/api/stories", () => ({
  createStory: mocks.createStory,
  deleteStory: mocks.deleteStory,
  updateStory: mocks.updateStory,
  uploadStoryCover: mocks.uploadStoryCover,
}))

vi.mock("@/i18n/formatters", () => ({
  useLocaleFormatters: () => ({ formatDate: (value: Date | string | number) => String(value) }),
}))

vi.mock("@/components/Layout", () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

vi.mock("@/components/motion/PageFadeIn", () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

vi.mock("@/components/media/SmartImage", () => ({
  default: ({ alt, srcRaw }: { alt: string; srcRaw: string }) => <img alt={alt} src={srcRaw} />,
}))

vi.mock("@/components/settings", () => ({
  Alert: ({ children }: { children: React.ReactNode }) => <div role="alert">{children}</div>,
  Button: ({
    as: Component = "button",
    children,
    leadingIcon: _leadingIcon,
    startIcon: _startIcon,
    loading: _loading,
    size: _size,
    variant: _variant,
    disabled: _disabled,
    ...props
  }: any) => <Component {...props}>{children}</Component>,
  CircularProgress: () => <div aria-label="loading" />,
  Divider: () => <hr />,
  SectionCard: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
  TextField: ({ label, multiline, ...props }: any) => (
    <label>
      {label}
      {multiline ? <textarea {...props} /> : <input {...props} />}
    </label>
  ),
}))

vi.mock("@/components/ui", () => ({
  Badge: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
  Card: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
  ConfirmDialog: ({
    open,
    title,
    confirmText,
    cancelText,
    onConfirm,
    onCancel,
  }: {
    open: boolean
    title: string
    confirmText: string
    cancelText: string
    onConfirm: () => void
    onCancel: () => void
  }) =>
    open ? (
      <div role="alertdialog" aria-label={title}>
        <button onClick={onCancel}>{cancelText}</button>
        <button onClick={onConfirm}>{confirmText}</button>
      </div>
    ) : null,
}))

const story = {
  id: "story-1",
  title: "Existing story",
  short_text: "Existing text",
  published_at: "2026-08-01T10:00:00.000Z",
  expires_at: "2026-08-02T10:00:00.000Z",
  is_active: true,
  created_at: "2026-07-31T10:00:00.000Z",
}

describe("StoriesAdmin", () => {
  beforeEach(() => {
    mocks.user = { id: "admin-1", role: "admin" }
    mocks.getStories.mockReset()
    mocks.createStory.mockReset()
    mocks.deleteStory.mockReset()
    mocks.updateStory.mockReset()
    mocks.uploadStoryCover.mockReset()
    mocks.getStories.mockResolvedValue({ data: [] })
    mocks.createStory.mockResolvedValue({ id: "created-story" })
    mocks.deleteStory.mockResolvedValue(undefined)
    mocks.updateStory.mockResolvedValue(undefined)
  })

  it("blocks non-administrators before fetching private stories", () => {
    mocks.user = { id: "student-1", role: "student" as const }

    render(<StoriesAdmin />)

    expect(screen.getByText("stories:notAuthorized")).toBeInTheDocument()
    expect(mocks.getStories).not.toHaveBeenCalled()
  })

  it("loads stories and performs unpublish and confirmed delete actions", async () => {
    mocks.getStories.mockResolvedValue({ data: [story] })

    render(<StoriesAdmin />)

    expect(await screen.findByText(story.title)).toBeInTheDocument()
    expect(mocks.getStories).toHaveBeenCalledWith("/stories")

    fireEvent.click(screen.getByRole("button", { name: "stories:list.actions.unpublish" }))
    await waitFor(() => {
      expect(mocks.updateStory).toHaveBeenCalledWith(story.id, { is_active: false })
    })

    fireEvent.click(screen.getByRole("button", { name: "common:buttons.delete" }))
    expect(screen.getByRole("alertdialog")).toBeInTheDocument()
    fireEvent.click(screen.getAllByRole("button", { name: "common:buttons.delete" }).at(-1)!)

    await waitFor(() => {
      expect(mocks.deleteStory).toHaveBeenCalledWith(story.id)
    })
  })

  it("validates required fields before creating a story", async () => {
    render(<StoriesAdmin />)
    await screen.findByText("stories:list.empty")

    fireEvent.click(screen.getByRole("button", { name: "common:buttons.submit" }))

    expect(screen.getByRole("alert")).toHaveTextContent("stories:errors.required")
    expect(mocks.createStory).not.toHaveBeenCalled()
  })

  it("submits a valid new story and refreshes the list", async () => {
    render(<StoriesAdmin />)
    await screen.findByText("stories:list.empty")

    fireEvent.change(screen.getByLabelText("stories:form.titleRu"), {
      target: { value: "New story" },
    })
    fireEvent.change(screen.getByLabelText("stories:form.shortTextRu"), {
      target: { value: "New story text" },
    })
    fireEvent.change(screen.getByLabelText("stories:form.publishedAt"), {
      target: { value: "2026-08-01T10:00" },
    })
    fireEvent.change(screen.getByLabelText("stories:form.expiresAt"), {
      target: { value: "2026-08-02T10:00" },
    })

    fireEvent.click(screen.getByRole("button", { name: "common:buttons.submit" }))

    await waitFor(() => {
      expect(mocks.createStory).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "New story",
          short_text: "New story text",
          is_active: true,
          published_at: expect.any(String),
          expires_at: expect.any(String),
        })
      )
    })
    expect(await screen.findByText("stories:form.success")).toBeInTheDocument()
    expect(mocks.getStories).toHaveBeenCalledTimes(2)
  })

  it("shows the API error when loading stories fails", async () => {
    mocks.getStories.mockRejectedValueOnce(new Error("story service unavailable"))

    render(<StoriesAdmin />)

    expect(await screen.findByRole("alert")).toHaveTextContent("story service unavailable")
    expect(screen.getByText("stories:list.empty")).toBeInTheDocument()
  })

  it("normalizes a non-array list response to the empty state", async () => {
    mocks.getStories.mockResolvedValueOnce({ data: { items: [] } })

    render(<StoriesAdmin />)

    expect(await screen.findByText("stories:list.empty")).toBeInTheDocument()
    expect(screen.getByText("stories:list.title")).toBeInTheDocument()
  })

  it("validates invalid and non-increasing form dates before submitting", async () => {
    render(<StoriesAdmin />)
    await screen.findByText("stories:list.empty")

    fireEvent.change(screen.getByLabelText("stories:form.titleRu"), {
      target: { value: "New story" },
    })
    fireEvent.change(screen.getByLabelText("stories:form.shortTextRu"), {
      target: { value: "New story text" },
    })
    fireEvent.change(screen.getByLabelText("stories:form.publishedAt"), {
      target: { value: "" },
    })
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.submit" }))

    expect(screen.getByRole("alert")).toHaveTextContent("stories:errors.invalidDate")
    expect(mocks.createStory).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText("stories:form.publishedAt"), {
      target: { value: "2026-08-02T10:00" },
    })
    fireEvent.change(screen.getByLabelText("stories:form.expiresAt"), {
      target: { value: "2026-08-01T10:00" },
    })
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.submit" }))

    expect(screen.getByRole("alert")).toHaveTextContent("stories:errors.expirationAfterPublish")
    expect(mocks.createStory).not.toHaveBeenCalled()
  })

  it("uploads a cover and includes optional form fields in the request", async () => {
    const createObjectUrl = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:story-cover")
    const revokeObjectUrl = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined)
    mocks.uploadStoryCover.mockResolvedValue({ url: "https://cdn.example/story.png" })

    render(<StoriesAdmin />)
    await screen.findByText("stories:list.empty")

    fireEvent.change(screen.getByLabelText("stories:form.titleRu"), {
      target: { value: "Новая история" },
    })
    fireEvent.change(screen.getByLabelText("stories:form.titleEn"), {
      target: { value: "New story" },
    })
    fireEvent.change(screen.getByLabelText("stories:form.shortTextRu"), {
      target: { value: "Текст" },
    })
    fireEvent.change(screen.getByLabelText("stories:form.shortTextEn"), {
      target: { value: "Text" },
    })
    fireEvent.change(screen.getByLabelText("stories:form.ctaUrl"), {
      target: { value: "https://example.com/story" },
    })
    fireEvent.change(screen.getByLabelText("common:buttons.uploadPhoto"), {
      target: {
        files: [new File(["image"], "story.png", { type: "image/png" })],
      },
    })

    expect(screen.getByAltText("stories:form.previewAlt")).toHaveAttribute(
      "src",
      "blob:story-cover"
    )
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.submit" }))

    await waitFor(() => {
      expect(mocks.uploadStoryCover).toHaveBeenCalledWith(expect.any(File))
      expect(mocks.createStory).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Новая история",
          short_text: "Текст",
          title_en: "New story",
          short_text_en: "Text",
          cta_url: "https://example.com/story",
          cover_url: "https://cdn.example/story.png",
          is_active: true,
        })
      )
    })

    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:story-cover")
    createObjectUrl.mockRestore()
    revokeObjectUrl.mockRestore()
  })

  it("surfaces a structured API error from cover upload", async () => {
    mocks.uploadStoryCover.mockRejectedValue({
      isAxiosError: true,
      response: { data: { detail: "cover rejected" } },
    })

    render(<StoriesAdmin />)
    await screen.findByText("stories:list.empty")
    fireEvent.change(screen.getByLabelText("stories:form.titleRu"), {
      target: { value: "New story" },
    })
    fireEvent.change(screen.getByLabelText("stories:form.shortTextRu"), {
      target: { value: "New story text" },
    })
    fireEvent.change(screen.getByLabelText("common:buttons.uploadPhoto"), {
      target: {
        files: [new File(["image"], "story.png", { type: "image/png" })],
      },
    })
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.submit" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("cover rejected")
    expect(mocks.createStory).not.toHaveBeenCalled()
  })

  it("handles timer validation, cover update, and delete cancellation", async () => {
    const createObjectUrl = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:item-cover")
    const revokeObjectUrl = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined)
    mocks.getStories.mockResolvedValue({
      data: [
        { ...story, cover_url: "https://cdn.example/old.png", cta_url: "https://example.com" },
      ],
    })
    mocks.uploadStoryCover.mockResolvedValue({ url: "https://cdn.example/new.png" })

    render(<StoriesAdmin />)
    expect(await screen.findByText(story.title)).toBeInTheDocument()

    const itemInputs = screen.getAllByLabelText("stories:list.actions.pickCover")
    fireEvent.change(itemInputs.at(-1)!, {
      target: { files: [new File(["not-an-image"], "story.txt", { type: "text/plain" })] },
    })
    expect(screen.getByRole("alert")).toHaveTextContent("stories:errors.invalidFileType")

    fireEvent.change(itemInputs.at(-1)!, {
      target: { files: [new File(["image"], "story.png", { type: "image/png" })] },
    })
    fireEvent.click(screen.getByRole("button", { name: "stories:list.actions.updateCover" }))
    await waitFor(() => {
      expect(mocks.uploadStoryCover).toHaveBeenCalledWith(expect.any(File))
      expect(mocks.updateStory).toHaveBeenCalledWith(story.id, {
        cover_url: "https://cdn.example/new.png",
      })
    })

    const timerInputs = screen.getAllByLabelText("stories:form.publishedAt")
    const expiryInputs = screen.getAllByLabelText("stories:form.expiresAt")
    fireEvent.change(timerInputs.at(-1)!, { target: { value: "2026-08-02T10:00" } })
    fireEvent.change(expiryInputs.at(-1)!, { target: { value: "2026-08-01T10:00" } })
    fireEvent.click(screen.getByRole("button", { name: "stories:list.actions.updateTimer" }))
    expect(screen.getByRole("alert")).toHaveTextContent("stories:errors.expirationAfterPublish")

    fireEvent.click(screen.getByRole("button", { name: "common:buttons.delete" }))
    expect(screen.getByRole("alertdialog")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.cancel" }))
    expect(screen.queryByRole("alertdialog")).toBeNull()

    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:item-cover")
    createObjectUrl.mockRestore()
    revokeObjectUrl.mockRestore()
  })

  it("covers item date errors, successful timer updates, refresh, and action failures", async () => {
    mocks.getStories.mockResolvedValue({ data: [story] })
    render(<StoriesAdmin />)
    expect(await screen.findByText(story.title)).toBeInTheDocument()

    mocks.getStories.mockClear()
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.refresh" }))
    await waitFor(() => expect(mocks.getStories).toHaveBeenCalledWith("/stories"))

    const publishedInput = screen.getAllByLabelText("stories:form.publishedAt").at(-1)!
    const expiryInput = screen.getAllByLabelText("stories:form.expiresAt").at(-1)!
    fireEvent.change(publishedInput, { target: { value: "" } })
    fireEvent.click(screen.getByRole("button", { name: "stories:list.actions.updateTimer" }))
    expect(screen.getByRole("alert")).toHaveTextContent("stories:errors.invalidDate")

    fireEvent.change(publishedInput, { target: { value: "2026-08-01T10:00" } })
    fireEvent.change(expiryInput, { target: { value: "2026-08-02T10:00" } })
    mocks.updateStory.mockResolvedValueOnce(undefined)
    fireEvent.click(screen.getByRole("button", { name: "stories:list.actions.updateTimer" }))
    await waitFor(() => {
      expect(mocks.updateStory).toHaveBeenCalledWith(story.id, {
        published_at: "2026-08-01T07:00:00.000Z",
        expires_at: "2026-08-02T07:00:00.000Z",
      })
    })

    mocks.updateStory.mockRejectedValueOnce({})
    fireEvent.click(screen.getByRole("button", { name: "stories:list.actions.unpublish" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("stories:errors.unpublishFailed")

    mocks.deleteStory.mockRejectedValueOnce({})
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.delete" }))
    fireEvent.click(screen.getAllByRole("button", { name: "common:buttons.delete" }).at(-1)!)
    expect(await screen.findByRole("alert")).toHaveTextContent("stories:errors.deleteFailed")
  })

  it("surfaces timer and item cover update failures", async () => {
    const createObjectUrl = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:failure-cover")
    const revokeObjectUrl = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined)
    mocks.getStories.mockResolvedValue({ data: [story] })
    const { unmount } = render(<StoriesAdmin />)
    expect(await screen.findByText(story.title)).toBeInTheDocument()

    mocks.updateStory.mockRejectedValueOnce({})
    fireEvent.click(screen.getByRole("button", { name: "stories:list.actions.updateTimer" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("stories:errors.updateFailed")

    mocks.uploadStoryCover.mockRejectedValueOnce(new Error("cover update failed"))
    const coverInput = screen.getAllByLabelText("stories:list.actions.pickCover").at(-1)!
    fireEvent.change(coverInput, {
      target: { files: [new File(["image"], "failure.png", { type: "image/png" })] },
    })
    fireEvent.click(screen.getByRole("button", { name: "stories:list.actions.updateCover" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("cover update failed")

    unmount()
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:failure-cover")
    createObjectUrl.mockRestore()
    revokeObjectUrl.mockRestore()
  })

  it("replaces form previews and handles an upload response without a URL", async () => {
    const createObjectUrl = vi
      .spyOn(URL, "createObjectURL")
      .mockReturnValueOnce("blob:first-cover")
      .mockReturnValueOnce("blob:second-cover")
    const revokeObjectUrl = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined)
    mocks.uploadStoryCover.mockResolvedValueOnce({})

    render(<StoriesAdmin />)
    await screen.findByText("stories:list.empty")
    const coverInput = screen.getByLabelText("common:buttons.uploadPhoto")
    const firstFile = new File(["first"], "first.png", { type: "image/png" })
    const secondFile = new File(["second"], "second.png", { type: "image/png" })

    fireEvent.change(coverInput, { target: { files: [] } })
    fireEvent.change(coverInput, { target: { files: [firstFile] } })
    expect(screen.getByText("Title")).toBeInTheDocument()
    expect(screen.getByText("Text")).toBeInTheDocument()
    fireEvent.change(coverInput, { target: { files: [secondFile] } })
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:first-cover")

    fireEvent.change(screen.getByLabelText("stories:form.titleRu"), {
      target: { value: "Story without returned cover" },
    })
    fireEvent.change(screen.getByLabelText("stories:form.shortTextRu"), {
      target: { value: "Short text" },
    })
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.submit" }))

    await waitFor(() => expect(mocks.createStory).toHaveBeenCalled())
    expect(mocks.createStory.mock.calls.at(-1)?.[0]).not.toHaveProperty("cover_url")
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:second-cover")
    createObjectUrl.mockRestore()
    revokeObjectUrl.mockRestore()
  })

  it("sends an empty cover URL when an item upload has no URL", async () => {
    const createObjectUrl = vi
      .spyOn(URL, "createObjectURL")
      .mockReturnValueOnce("blob:item-first")
      .mockReturnValueOnce("blob:item-no-url")
    const revokeObjectUrl = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined)
    mocks.getStories.mockResolvedValue({ data: [story] })
    mocks.uploadStoryCover.mockResolvedValueOnce({})

    render(<StoriesAdmin />)
    expect(await screen.findByText(story.title)).toBeInTheDocument()
    const coverInput = screen.getAllByLabelText("stories:list.actions.pickCover").at(-1)!
    fireEvent.change(coverInput, { target: { files: [] } })
    fireEvent.click(screen.getByRole("button", { name: "stories:list.actions.updateCover" }))
    expect(mocks.uploadStoryCover).not.toHaveBeenCalled()

    fireEvent.change(coverInput, {
      target: { files: [new File(["image"], "item-first.png", { type: "image/png" })] },
    })
    fireEvent.change(coverInput, {
      target: { files: [new File(["image"], "item-second.png", { type: "image/png" })] },
    })
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:item-first")
    fireEvent.click(screen.getByRole("button", { name: "stories:list.actions.updateCover" }))

    await waitFor(() => {
      expect(mocks.updateStory).toHaveBeenCalledWith(story.id, { cover_url: "" })
    })
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:item-no-url")
    createObjectUrl.mockRestore()
    revokeObjectUrl.mockRestore()
  })

  it("uses a raw Axios string detail for cover upload errors", async () => {
    mocks.uploadStoryCover.mockRejectedValueOnce({
      isAxiosError: true,
      response: { data: "raw cover rejection" },
    })

    render(<StoriesAdmin />)
    await screen.findByText("stories:list.empty")
    fireEvent.change(screen.getByLabelText("stories:form.titleRu"), {
      target: { value: "Raw error story" },
    })
    fireEvent.change(screen.getByLabelText("stories:form.shortTextRu"), {
      target: { value: "Text" },
    })
    fireEvent.change(screen.getByLabelText("common:buttons.uploadPhoto"), {
      target: { files: [new File(["image"], "raw.png", { type: "image/png" })] },
    })
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.submit" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("raw cover rejection")
    expect(mocks.createStory).not.toHaveBeenCalled()
  })
})
