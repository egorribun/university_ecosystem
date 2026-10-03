import { act, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider, notifyManager } from "@tanstack/react-query"
import { http, HttpResponse } from "msw"
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest"

import { NewsComments } from "@/components/news/NewsComments"
import {
  useNewsInteraction,
  type NewsComment,
  type NewsInteractions,
} from "@/hooks/useNewsInteraction"
import { server } from "@/tests/mocks/server"
import type { User } from "@/types/User"

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { id: "019961d3-bb00-7000-8000-000000000010", full_name: "Comment Author" },
  }),
}))
vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const NEWS_ID = "019961d3-bb00-7000-8000-000000000020"
const CONTENT = "Looking forward to the research opening."
const PERSISTED: NewsComment = {
  id: "019961d3-bb00-7000-8000-000000000001",
  user_id: "019961d3-bb00-7000-8000-000000000010",
  user_name: "Comment Author",
  content: "Existing comment",
  created_at: "2026-10-01T12:00:00Z",
}
const CREATED: NewsComment = {
  ...PERSISTED,
  id: "019961d3-bb00-7000-8000-000000000002",
  content: CONTENT,
  created_at: "2026-10-03T12:00:00Z",
}
const INITIAL: NewsInteractions = {
  likes_count: 3,
  is_liked: false,
  comments: [PERSISTED],
  comments_count: 1,
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((res) => {
    resolve = res
  })
  return { promise, resolve }
}

beforeAll(() => {
  notifyManager.setNotifyFunction((callback) => act(callback))
})
afterAll(() => {
  notifyManager.setNotifyFunction((callback) => callback())
})

function renderComments(role: User["role"] = "student") {
  const post = deferred<Response>()
  const refetch = deferred<void>()
  const posted: unknown[] = []
  const actions: { method: string; path: string; body?: unknown }[] = []
  let state = INITIAL
  let getCount = 0
  server.use(
    http.get(`*/news/${NEWS_ID}/interactions`, async () => {
      getCount += 1
      if (getCount > 1) await refetch.promise
      return HttpResponse.json(state)
    }),
    http.post(`*/news/${NEWS_ID}/comment`, async ({ request }) => {
      posted.push(await request.json())
      return post.promise
    }),
    http.patch("*/news/comments/:commentId", async ({ request, params }) => {
      const body = (await request.json()) as { content: string }
      actions.push({ method: "PATCH", path: new URL(request.url).pathname, body })
      state = {
        ...state,
        comments: state.comments.map((comment) =>
          comment.id === params.commentId ? { ...comment, content: body.content } : comment
        ),
      }
      return HttpResponse.json({ ...CREATED, content: body.content })
    }),
    http.delete("*/news/comments/:commentId", ({ request, params }) => {
      actions.push({ method: "DELETE", path: new URL(request.url).pathname })
      state = {
        ...state,
        comments: state.comments.filter((comment) => comment.id !== params.commentId),
        comments_count: state.comments_count! - 1,
      }
      return HttpResponse.json({ ok: true })
    })
  )
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  function Harness() {
    const interaction = useNewsInteraction(NEWS_ID)
    return (
      <NewsComments
        comments={interaction.interactions?.comments ?? []}
        user={{ id: "019961d3-bb00-7000-8000-000000000010", role }}
        isCommenting={interaction.isCommenting}
        addComment={interaction.addComment}
        updateComment={interaction.updateComment}
        deleteComment={interaction.deleteComment}
        t={(key) => key}
        getMoscowDate={(date) => date}
      />
    )
  }
  const view = render(
    <QueryClientProvider client={client}>
      <Harness />
    </QueryClientProvider>
  )
  const user = userEvent.setup()
  return {
    user,
    client,
    actions,
    post,
    refetch,
    async submit() {
      await screen.findByText(PERSISTED.content)
      await user.type(screen.getByRole("textbox", { name: "news:form.commentAriaLabel" }), CONTENT)
      await user.click(screen.getByRole("button", { name: "news:actions.postComment" }))
      await waitFor(() => expect(posted).toEqual([{ content: CONTENT }]))
      await screen.findByText(CONTENT)
    },
    async finishPost() {
      state = { ...INITIAL, comments: [PERSISTED, CREATED], comments_count: 2 }
      await act(async () => post.resolve(HttpResponse.json(CREATED)))
      await waitFor(() => expect(getCount).toBeGreaterThan(1))
      await waitFor(() => expect(client.isMutating()).toBe(0))
    },
    async dispose() {
      view.unmount()
      await act(async () => {
        refetch.resolve()
        post.resolve(new HttpResponse(null, { status: 500 }))
      })
      await waitFor(() => expect(client.isMutating()).toBe(0))
      client.clear()
    },
  }
}

function row(content: string) {
  return within(screen.getByText(content).parentElement!)
}

describe("NewsComments pending actions", () => {
  for (const role of ["student", "admin"] as const) {
    it.each(["posting", "refetching"] as const)(
      `keeps the ${role}'s temporary comment read-only while %s`,
      async (phase) => {
        const fixture = renderComments(role)
        try {
          await fixture.submit()
          if (phase === "refetching") {
            await fixture.finishPost()
            // The composer is usable again even though GET has not supplied
            // the persisted comment ID. A global isCommenting guard is insufficient.
            await fixture.user.type(
              screen.getByRole("textbox", { name: "news:form.commentAriaLabel" }),
              "Next comment"
            )
            await waitFor(() =>
              expect(screen.getByRole("button", { name: "news:actions.postComment" })).toBeEnabled()
            )
          }

          const pendingRow = row(CONTENT)
          const edit = pendingRow.getByRole("button", { name: "news:actions.editComment" })
          const remove = pendingRow.getByRole("button", { name: "news:actions.deleteComment" })
          await fixture.user.click(edit)
          await fixture.user.click(remove)
          expect(
            screen.queryByRole("textbox", { name: "news:form.editCommentAriaLabel" })
          ).not.toBeInTheDocument()
          expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument()
          expect(edit).toBeDisabled()
          expect(remove).toBeDisabled()
          expect(pendingRow.getByText("Comment Author")).toBeVisible()
          expect(fixture.actions).toEqual([])

          // A pending new comment must not freeze previously persisted rows.
          const existing = row(PERSISTED.content)
          expect(existing.getByRole("button", { name: "news:actions.editComment" })).toBeEnabled()
          expect(existing.getByRole("button", { name: "news:actions.deleteComment" })).toBeEnabled()
          await fixture.user.click(
            existing.getByRole("button", { name: "news:actions.editComment" })
          )
          expect(
            screen.getByRole("textbox", { name: "news:form.editCommentAriaLabel" })
          ).toHaveValue(PERSISTED.content)
          await fixture.user.click(screen.getByRole("button", { name: "common:buttons.cancel" }))
          await fixture.user.click(
            row(PERSISTED.content).getByRole("button", { name: "news:actions.deleteComment" })
          )
          await fixture.user.click(
            within(screen.getByRole("alertdialog")).getByRole("button", {
              name: "common:buttons.cancel",
            })
          )
          expect(fixture.actions).toEqual([])
        } finally {
          await fixture.dispose()
        }
      }
    )
  }

  it("enables edit and delete after reconciliation and sends the persisted ID", async () => {
    const fixture = renderComments()
    try {
      await fixture.submit()
      await fixture.finishPost()
      await act(async () => fixture.refetch.resolve())
      await waitFor(() => expect(fixture.client.isFetching()).toBe(0))
      const edit = row(CONTENT).getByRole("button", { name: "news:actions.editComment" })
      await waitFor(() => expect(edit).toBeEnabled())
      expect(row(CONTENT).getByText(CREATED.created_at)).toBeVisible()
      await fixture.user.click(edit)
      const editor = screen.getByRole("textbox", { name: "news:form.editCommentAriaLabel" })
      await fixture.user.clear(editor)
      await fixture.user.type(editor, "Updated research comment")
      await fixture.user.click(screen.getByRole("button", { name: "common:buttons.save" }))
      await waitFor(() =>
        expect(fixture.actions).toEqual([
          {
            method: "PATCH",
            path: `/news/comments/${CREATED.id}`,
            body: { content: "Updated research comment" },
          },
        ])
      )
      await waitFor(() => expect(fixture.client.isMutating()).toBe(0))
      await waitFor(() => expect(fixture.client.isFetching()).toBe(0))
      await fixture.user.click(
        row("Updated research comment").getByRole("button", { name: "news:actions.deleteComment" })
      )
      await fixture.user.click(
        within(screen.getByRole("alertdialog")).getByRole("button", {
          name: "common:buttons.delete",
        })
      )
      await waitFor(() =>
        expect(fixture.actions).toEqual([
          {
            method: "PATCH",
            path: `/news/comments/${CREATED.id}`,
            body: { content: "Updated research comment" },
          },
          { method: "DELETE", path: `/news/comments/${CREATED.id}` },
        ])
      )
      await waitFor(() =>
        expect(screen.queryByText("Updated research comment")).not.toBeInTheDocument()
      )
      expect(screen.getByText(PERSISTED.content)).toBeVisible()
    } finally {
      await fixture.dispose()
    }
  })

  it("removes the temporary row when posting fails while the refetch is still pending", async () => {
    const fixture = renderComments()
    try {
      await fixture.submit()
      await act(async () => fixture.post.resolve(new HttpResponse(null, { status: 500 })))
      await waitFor(() => expect(screen.queryByText(CONTENT)).not.toBeInTheDocument())
      expect(fixture.client.isFetching()).toBe(1)
      expect(
        row(PERSISTED.content).getByRole("button", { name: "news:actions.editComment" })
      ).toBeEnabled()
      expect(
        row(PERSISTED.content).getByRole("button", { name: "news:actions.deleteComment" })
      ).toBeEnabled()
      expect(fixture.actions).toEqual([])
    } finally {
      await fixture.dispose()
    }
  })
})
