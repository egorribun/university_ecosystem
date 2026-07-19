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
})
