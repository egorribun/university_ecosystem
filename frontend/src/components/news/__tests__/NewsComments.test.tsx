import { fireEvent, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

import { NewsComments } from "@/components/news/NewsComments"
import type { NewsComment } from "@/hooks/useNewsInteraction"
import type { User } from "@/types/User"

const SAMPLE_COMMENTS: NewsComment[] = [
  {
    id: "c1",
    content: "Great write-up on the new research center.",
    user_id: "u2",
    user_name: "Anna Petrova",
    created_at: "2026-05-20T09:30:00Z",
  },
  {
    id: "c2",
    content: "Any word on enrollment caps?",
    user_id: "u3",
    user_name: "Ivan Sokolov",
    created_at: "2026-05-21T14:15:00Z",
  },
]

const adminUser = { id: "u1", role: "admin" } as Pick<User, "id" | "role">

const baseProps = {
  comments: SAMPLE_COMMENTS,
  user: adminUser,
  isCommenting: false,
  addComment: vi.fn(),
  updateComment: vi.fn(),
  deleteComment: vi.fn(),
  t: (key: string) => key,
  getMoscowDate: (date: string) => date,
}

describe("NewsComments", () => {
  it("renders heading, count, and each comment", () => {
    render(<NewsComments {...baseProps} />)
    expect(screen.getByRole("heading", { name: "news:sections.comments" })).toBeInTheDocument()
    expect(screen.getByText("2")).toBeInTheDocument()
    expect(screen.getByText("Anna Petrova")).toBeInTheDocument()
    expect(screen.getByText("Great write-up on the new research center.")).toBeInTheDocument()
    expect(screen.getByText("Any word on enrollment caps?")).toBeInTheDocument()
  })

  it("shows the empty state when there are no comments", () => {
    render(<NewsComments {...baseProps} comments={[]} />)
    expect(screen.getByText("news:states.noComments")).toBeInTheDocument()
  })

  it("hides the comment form when there is no user", () => {
    render(<NewsComments {...baseProps} user={null} />)
    expect(screen.queryByLabelText("news:form.commentAriaLabel")).not.toBeInTheDocument()
  })

  it("posts a new comment", async () => {
    const user = userEvent.setup()
    const addComment = vi.fn()
    render(<NewsComments {...baseProps} addComment={addComment} />)
    const textarea = screen.getByLabelText("news:form.commentAriaLabel")
    await user.type(textarea, "Looking forward to it!")
    await user.click(screen.getByRole("button", { name: "news:actions.postComment" }))
    expect(addComment).toHaveBeenCalledWith("Looking forward to it!")
  })

  it("does not submit whitespace and supports cancelling an empty edit", async () => {
    const user = userEvent.setup()
    const addComment = vi.fn()
    render(<NewsComments {...baseProps} addComment={addComment} />)

    const textarea = screen.getByLabelText("news:form.commentAriaLabel")
    await user.type(textarea, "   ")
    expect(screen.getByRole("button", { name: "news:actions.postComment" })).toBeDisabled()
    expect(addComment).not.toHaveBeenCalled()

    await user.click(screen.getAllByLabelText("news:actions.editComment")[0]!)
    const editBox = screen.getByLabelText("news:form.editCommentAriaLabel")
    await user.clear(editBox)
    expect(screen.getByRole("button", { name: "common:buttons.save" })).toBeDisabled()
    await user.click(screen.getByRole("button", { name: "common:buttons.cancel" }))
    expect(screen.queryByLabelText("news:form.editCommentAriaLabel")).not.toBeInTheDocument()
  })

  it("hides owner actions for a different non-admin user", () => {
    render(<NewsComments {...baseProps} user={{ id: "other", role: "student" }} />)
    expect(screen.queryByLabelText("news:actions.editComment")).not.toBeInTheDocument()
    expect(screen.queryByLabelText("news:actions.deleteComment")).not.toBeInTheDocument()
  })

  it("enters inline edit mode and saves an update", async () => {
    const user = userEvent.setup()
    const updateComment = vi.fn()
    render(<NewsComments {...baseProps} updateComment={updateComment} />)
    await user.click(screen.getAllByLabelText("news:actions.editComment")[0]!)
    const editBox = screen.getByLabelText("news:form.editCommentAriaLabel")
    await user.type(editBox, " (edited)")
    await user.click(screen.getByRole("button", { name: "common:buttons.save" }))
    expect(updateComment).toHaveBeenCalledOnce()
    expect(updateComment.mock.calls[0]![0]).toBe("c1")
  })

  it("confirms before deleting a comment", async () => {
    const user = userEvent.setup()
    const deleteComment = vi.fn()
    render(<NewsComments {...baseProps} deleteComment={deleteComment} />)
    await user.click(screen.getAllByLabelText("news:actions.deleteComment")[0]!)
    let dialog = screen.getByRole("alertdialog")
    await user.click(within(dialog).getByRole("button", { name: "common:buttons.cancel" }))
    expect(deleteComment).not.toHaveBeenCalled()

    await user.click(screen.getAllByLabelText("news:actions.deleteComment")[0]!)
    dialog = screen.getByRole("alertdialog")
    await user.click(within(dialog).getByRole("button", { name: "common:buttons.delete" }))
    expect(deleteComment).toHaveBeenCalledWith("c1")
  })

  it("shows warning and error character-count thresholds for new and edited comments", async () => {
    const user = userEvent.setup()
    render(<NewsComments {...baseProps} />)

    const newComment = screen.getByLabelText("news:form.commentAriaLabel")
    fireEvent.change(newComment, { target: { value: "x".repeat(400) } })
    expect(screen.getByText("400/500")).toHaveClass("text-warning-text")
    fireEvent.change(newComment, { target: { value: "x".repeat(475) } })
    expect(screen.getByText("475/500")).toHaveClass("text-(--error-text)")

    await user.click(screen.getAllByLabelText("news:actions.editComment")[0]!)
    const editBox = screen.getByLabelText("news:form.editCommentAriaLabel")
    fireEvent.change(editBox, { target: { value: "x".repeat(400) } })
    expect(screen.getByText("400/500")).toHaveClass("text-warning-text")
    fireEvent.change(editBox, { target: { value: "x".repeat(475) } })
    expect(screen.getAllByText("475/500")).toHaveLength(2)
    expect(
      screen
        .getAllByText("475/500")
        .every((element) => element.className.includes("text-(--error-text)"))
    ).toBe(true)
  })
})
