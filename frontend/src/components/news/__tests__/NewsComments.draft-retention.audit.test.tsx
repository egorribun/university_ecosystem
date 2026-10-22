import { act, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

import { NewsComments } from "@/components/news/NewsComments"
import type { User } from "@/types/User"

const author = { id: "commenter-1", role: "student" } as Pick<User, "id" | "role">
const draftText = "A comment that must survive a failed post."

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function renderForm(addComment: (content: string) => void) {
  return render(
    <NewsComments
      comments={[]}
      user={author}
      isCommenting={false}
      addComment={addComment}
      updateComment={vi.fn()}
      deleteComment={vi.fn()}
      t={(key) => key}
      getMoscowDate={(date) => date}
    />
  )
}

describe("AUD-216 news comment draft lifecycle", () => {
  it("retains the draft while a post is pending and after the deferred request fails", async () => {
    const user = userEvent.setup()
    const attempt = deferred<void>()
    const settled = attempt.promise.then(
      () => ({ kind: "success" as const }),
      (error: unknown) => ({ kind: "failure" as const, error })
    )
    const addComment = vi.fn(() => attempt.promise)
    renderForm(addComment)

    const textarea = screen.getByRole("textbox", { name: "news:form.commentAriaLabel" })
    await user.type(textarea, draftText)
    await user.click(screen.getByRole("button", { name: "news:actions.postComment" }))

    const draftRetainedWhilePending =
      textarea instanceof HTMLTextAreaElement && textarea.value === draftText
    const failure = new Error("post failed")
    let outcome: Awaited<typeof settled> | undefined
    await act(async () => {
      attempt.reject(failure)
      outcome = await settled
    })

    expect(outcome).toEqual({ kind: "failure", error: failure })
    expect(addComment).toHaveBeenCalledWith(draftText)
    expect(draftRetainedWhilePending).toBe(true)
    expect(textarea).toHaveValue(draftText)
  })

  it("clears the draft only after the deferred post succeeds", async () => {
    const user = userEvent.setup()
    const attempt = deferred<void>()
    const settled = attempt.promise.then(() => undefined)
    const addComment = vi.fn(() => attempt.promise)
    renderForm(addComment)

    const textarea = screen.getByRole("textbox", { name: "news:form.commentAriaLabel" })
    await user.type(textarea, draftText)
    await user.click(screen.getByRole("button", { name: "news:actions.postComment" }))

    const draftRetainedWhilePending =
      textarea instanceof HTMLTextAreaElement && textarea.value === draftText
    await act(async () => {
      attempt.resolve()
      await settled
    })

    expect(addComment).toHaveBeenCalledWith(draftText)
    expect(draftRetainedWhilePending).toBe(true)
    expect(textarea).toHaveValue("")
  })

  it("keeps a newer draft typed during a pending post when that post succeeds", async () => {
    const user = userEvent.setup()
    const attempt = deferred<void>()
    const settled = attempt.promise.then(() => undefined)
    const addComment = vi.fn(() => attempt.promise)
    renderForm(addComment)

    const textarea = screen.getByRole("textbox", { name: "news:form.commentAriaLabel" })
    await user.type(textarea, draftText)
    await user.click(screen.getByRole("button", { name: "news:actions.postComment" }))

    expect(textarea).toHaveValue(draftText)
    const newerDraft = "A newer draft typed while the post is pending."
    await user.clear(textarea)
    await user.type(textarea, newerDraft)
    expect(textarea).toHaveValue(newerDraft)

    await act(async () => {
      attempt.resolve()
      await settled
    })

    expect(addComment).toHaveBeenCalledWith(draftText)
    expect(textarea).toHaveValue(newerDraft)
  })
})
