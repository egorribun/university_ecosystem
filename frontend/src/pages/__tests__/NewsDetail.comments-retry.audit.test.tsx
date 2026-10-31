import { QueryClient, QueryClientProvider, notifyManager } from "@tanstack/react-query"
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest"

import { NewsComments } from "@/components/news/NewsComments"
import { acceptBrowserSessionGeneration, invalidateSessionEpoch } from "@/stores/sessionEpoch"
import { useAuthStore } from "@/stores/useAuthStore"
import { server } from "@/tests/mocks/server"
import type { UserState } from "@/types/Auth"
import NewsDetail from "../NewsDetail"

const fixture = vi.hoisted(() => ({
  newsId: "019961d3-bb00-7000-8000-000000000020",
  user: null as { id: string; full_name: string; role: "student" } | null,
}))

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => vi.fn(),
  useParams: () => ({ id: fixture.newsId }),
}))
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: fixture.user }) }))
vi.mock("@/contexts/LanguageContext", () => ({ useLanguage: () => ({ language: "en" }) }))
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }))
vi.mock("@/hooks/useMediaQuery", () => ({ default: () => false }))
vi.mock("@/hooks/useBookmarks", () => ({
  useBookmarks: () => ({ isBookmarked: () => false, toggleBookmark: vi.fn() }),
}))
vi.mock("@/hooks/useRelatedNews", () => ({ useRelatedNews: () => [] }))
vi.mock("@/hooks/useArticleNavigation", () => ({
  useArticleNavigation: () => ({ prevId: null, nextId: null, prevTitle: null, nextTitle: null }),
}))
vi.mock("@/hooks/useSwipe", () => ({ useSwipe: () => ({}) }))
vi.mock("@/hooks/useShare", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/hooks/useShare")>()),
  useShare: () => ({
    sharing: false,
    shareDialogOpen: false,
    setShareDialogOpen: vi.fn(),
    copyingLink: false,
    copiedLink: false,
    shareOptions: [],
    handleShare: vi.fn(),
    handleCopyLink: vi.fn(),
  }),
}))
vi.mock("@/utils/newsTransition", () => ({ setNewsHeroId: vi.fn() }))
vi.mock("@/components/ui/SEO", () => ({ SEO: () => null }))
vi.mock("@/components/news/NewsBackdrop", () => ({ NewsBackdrop: () => null }))
vi.mock("@/components/news/NewsDetailHeader", () => ({ NewsDetailHeader: () => null }))
vi.mock("@/components/news/NewsDetailHero", () => ({ NewsDetailHero: () => null }))
vi.mock("@/components/news/NewsDetailBody", () => ({ NewsDetailBody: () => null }))
vi.mock("@/components/news/NewsDetailNavigation", () => ({ NewsDetailNavigation: () => null }))
vi.mock("@/components/news/NewsDetailEditDialog", () => ({ NewsDetailEditDialog: () => null }))
vi.mock("@/components/news/RelatedNews", () => ({ RelatedNews: () => null }))
vi.mock("@/components/ui/ConfirmDialog", () => ({
  ConfirmDialog: ({
    open,
    onConfirm,
    confirmText,
  }: {
    open: boolean
    onConfirm: () => void
    confirmText: string
  }) => (open ? <button onClick={onConfirm}>{confirmText}</button> : null),
}))
vi.mock("@/components/settings", () => ({
  Alert: () => null,
  Dialog: () => null,
  DialogActions: () => null,
  DialogContent: () => null,
  DialogTitle: () => null,
  Snackbar: () => null,
}))

const comments = Array.from({ length: 41 }, (_, index) => ({
  id: `019961d3-bb00-7000-8000-${String(index).padStart(12, "0")}`,
  user_id: "019961d3-bb00-7000-8000-000000000010",
  user_name: "Comment Author",
  content: `Comment number ${index}`,
  created_at: "2026-10-01T12:00:00Z",
}))

function deferred() {
  let resolve!: () => void
  const promise = new Promise<void>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

function seedDetail(client: QueryClient, mode: "authenticated" | "anonymous", count: number) {
  const detailKey =
    mode === "anonymous"
      ? ["news", "anonymous-detail", fixture.newsId, "en"]
      : ["news", fixture.newsId, "en"]
  client.setQueryData(detailKey, {
    id: fixture.newsId,
    title: "Article",
    content: "Body",
    created_at: "2026-10-01T12:00:00Z",
    image_url_optimized: null,
    likes_count: 0,
    is_liked: false,
    comments_count: count,
  })
}

const cursorAfterFirst = "1790856000123456:019961d3-bb00-7000-8000-000000000019"
const cursorAfterSecond = "1790856000123456:019961d3-bb00-7000-8000-000000000039"

beforeAll(() => {
  notifyManager.setNotifyFunction((callback) => act(callback))
})
afterAll(() => {
  notifyManager.setNotifyFunction((callback) => callback())
})
beforeEach(() => {
  window.localStorage.clear()
  acceptBrowserSessionGeneration()
  invalidateSessionEpoch()
})
afterEach(() => {
  cleanup()
  fixture.user = null
  useAuthStore.setState({ user: null, loading: true })
  window.localStorage.clear()
})

describe("NewsDetail comment page recovery", () => {
  it.each([
    ["authenticated", "422"],
    ["anonymous", "422"],
    ["anonymous", "network"],
  ] as const)(
    "reports a %s reader's %s failure and retries without losing loaded comments",
    async (mode, failure) => {
      fixture.user =
        mode === "authenticated"
          ? {
              id: "019961d3-bb00-7000-8000-000000000010",
              full_name: "Comment Author",
              role: "student",
            }
          : null
      useAuthStore.setState({ user: fixture.user as UserState | null, loading: false })
      const offsets: number[] = []
      let rejectSecondPage = true
      server.use(
        http.get(`*/news/${fixture.newsId}`, () =>
          HttpResponse.json({
            id: fixture.newsId,
            title: "Article",
            content: "Body",
            created_at: "2026-10-01T12:00:00Z",
            image_url_optimized: null,
            likes_count: 4,
            is_liked: false,
            comments_count: comments.length,
          })
        ),
        http.get(`*/news/${fixture.newsId}/interactions`, ({ request }) => {
          const params = new URL(request.url).searchParams
          const offset = Number(params.get("offset"))
          const limit = Number(params.get("limit"))
          offsets.push(offset)
          if (offset === 20 && rejectSecondPage) {
            rejectSecondPage = false
            if (failure === "network") return HttpResponse.error()
            return HttpResponse.json(
              {
                detail: [{ loc: ["query", "offset"], msg: "Invalid offset", type: "value_error" }],
              },
              { status: 422 }
            )
          }
          return HttpResponse.json({
            likes_count: 4,
            is_liked: false,
            comments: comments.slice(offset, offset + limit),
            comments_count: comments.length,
          })
        })
      )

      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      const user = userEvent.setup()
      const view = render(
        <QueryClientProvider client={client}>
          <NewsDetail />
        </QueryClientProvider>
      )
      try {
        const section = await screen.findByRole("region", { name: "news:sections.comments" })
        await within(section).findByText("Comment number 19")
        if (mode === "authenticated") {
          await user.type(
            screen.getByRole("textbox", { name: "news:form.commentAriaLabel" }),
            "Draft"
          )
        }

        await user.click(screen.getByRole("button", { name: "news:actions.loadMoreComments" }))
        expect(await screen.findByRole("alert", {}, { timeout: 4000 })).toHaveTextContent(
          "news:states.commentsPageLoadError"
        )
        expect(within(section).getByText("Comment number 0")).toBeVisible()
        expect(within(section).getByText("Comment number 19")).toBeVisible()
        expect(within(section).queryByText("Comment number 20")).not.toBeInTheDocument()
        if (mode === "authenticated") {
          expect(screen.getByRole("textbox", { name: "news:form.commentAriaLabel" })).toHaveValue(
            "Draft"
          )
        }

        await user.click(screen.getByRole("button", { name: "news:actions.loadMoreComments" }))
        await within(section).findByText("Comment number 39")
        expect(screen.queryByRole("alert")).not.toBeInTheDocument()
        await user.click(screen.getByRole("button", { name: "news:actions.loadMoreComments" }))
        await within(section).findByText("Comment number 40")
        expect(screen.queryByRole("button", { name: "news:actions.loadMoreComments" })).toBeNull()
        expect(offsets).toEqual([0, 20, 20, 40])
        for (const comment of comments) {
          expect(within(section).getAllByText(comment.content)).toHaveLength(1)
        }
        if (mode === "authenticated") {
          expect(screen.getByRole("textbox", { name: "news:form.commentAriaLabel" })).toHaveValue(
            "Draft"
          )
        }
      } finally {
        view.unmount()
        client.clear()
      }
    }
  )

  it.each(["authenticated", "anonymous"] as const)(
    "keeps a seeded summary and draft while the first %s comment request fails and retries",
    async (mode) => {
      fixture.user =
        mode === "authenticated"
          ? {
              id: "019961d3-bb00-7000-8000-000000000010",
              full_name: "Comment Author",
              role: "student",
            }
          : null
      useAuthStore.setState({ user: fixture.user as UserState | null, loading: false })
      const firstRequest = deferred()
      let calls = 0
      server.use(
        http.get(`*/news/${fixture.newsId}/interactions`, async () => {
          calls += 1
          if (calls === 1) {
            await firstRequest.promise
            return HttpResponse.json(
              {
                detail: [{ loc: ["query", "offset"], msg: "Invalid offset", type: "value_error" }],
              },
              { status: 422 }
            )
          }
          return HttpResponse.json({
            likes_count: 4,
            is_liked: false,
            comments: [comments[0]],
            comments_count: 1,
          })
        })
      )

      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      const detailKey =
        mode === "anonymous"
          ? ["news", "anonymous-detail", fixture.newsId, "en"]
          : ["news", fixture.newsId, "en"]
      client.setQueryData(detailKey, {
        id: fixture.newsId,
        title: "Article",
        content: "Body",
        created_at: "2026-10-01T12:00:00Z",
        image_url_optimized: null,
        likes_count: 4,
        is_liked: false,
        comments_count: 1,
      })
      const user = userEvent.setup()
      const view = render(
        <QueryClientProvider client={client}>
          <NewsDetail />
        </QueryClientProvider>
      )
      try {
        const section = await screen.findByRole("region", { name: "news:sections.comments" })
        await waitFor(() => expect(calls).toBe(1))
        expect(within(section).queryByText("news:states.noComments")).not.toBeInTheDocument()
        expect(within(section).getByRole("status")).toHaveTextContent("news:states.loadingComments")
        expect(within(section).getByRole("heading").parentElement).toHaveTextContent("1")
        if (mode === "authenticated") {
          await user.type(
            within(section).getByRole("textbox", { name: "news:form.commentAriaLabel" }),
            "Draft"
          )
        }

        await act(async () => firstRequest.resolve())
        expect(await within(section).findByRole("alert")).toHaveTextContent(
          "news:states.commentsLoadError"
        )
        expect(within(section).queryByText("news:states.noComments")).not.toBeInTheDocument()
        expect(within(section).getByRole("heading").parentElement).toHaveTextContent("1")
        if (mode === "authenticated") {
          expect(
            within(section).getByRole("textbox", { name: "news:form.commentAriaLabel" })
          ).toHaveValue("Draft")
        }

        await user.click(within(section).getByRole("button", { name: "common:statuses.tryAgain" }))
        await within(section).findByText("Comment number 0")
        expect(within(section).queryByRole("alert")).not.toBeInTheDocument()
        expect(calls).toBe(2)
        if (mode === "authenticated") {
          expect(
            within(section).getByRole("textbox", { name: "news:form.commentAriaLabel" })
          ).toHaveValue("Draft")
        }
      } finally {
        await act(async () => firstRequest.resolve())
        view.unmount()
        client.clear()
      }
    }
  )

  it("shows the empty state only after the first comment response confirms it", async () => {
    useAuthStore.setState({ user: null, loading: false })
    const firstRequest = deferred()
    let requested = false
    server.use(
      http.get(`*/news/${fixture.newsId}/interactions`, async () => {
        requested = true
        await firstRequest.promise
        return HttpResponse.json({
          likes_count: 0,
          is_liked: false,
          comments: [],
          comments_count: 0,
        })
      })
    )
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    client.setQueryData(["news", "anonymous-detail", fixture.newsId, "en"], {
      id: fixture.newsId,
      title: "Article",
      content: "Body",
      created_at: "2026-10-01T12:00:00Z",
      image_url_optimized: null,
      likes_count: 0,
      is_liked: false,
      comments_count: 0,
    })
    const view = render(
      <QueryClientProvider client={client}>
        <NewsDetail />
      </QueryClientProvider>
    )
    try {
      const section = await screen.findByRole("region", { name: "news:sections.comments" })
      await waitFor(() => expect(requested).toBe(true))
      expect(within(section).queryByText("news:states.noComments")).not.toBeInTheDocument()
      await act(async () => firstRequest.resolve())
      await within(section).findByText("news:states.noComments")
      expect(within(section).queryByRole("status")).not.toBeInTheDocument()
    } finally {
      await act(async () => firstRequest.resolve())
      view.unmount()
      client.clear()
    }
  })

  it("keeps legacy cached comments and a draft when their background refresh fails", async () => {
    fixture.user = {
      id: "019961d3-bb00-7000-8000-000000000010",
      full_name: "Comment Author",
      role: "student",
    }
    useAuthStore.setState({ user: fixture.user as UserState, loading: false })
    let calls = 0
    server.use(
      http.get(`*/news/${fixture.newsId}/interactions`, () => {
        calls += 1
        return HttpResponse.json(
          { detail: [{ loc: ["query", "offset"], msg: "Invalid offset", type: "value_error" }] },
          { status: 422 }
        )
      })
    )
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    client.setQueryData(["news", fixture.newsId, "en"], {
      id: fixture.newsId,
      title: "Article",
      content: "Body",
      created_at: "2026-10-01T12:00:00Z",
      image_url_optimized: null,
      likes_count: 0,
      is_liked: false,
      comments_count: 1,
    })
    client.setQueryData(["news", fixture.newsId, "interactions"], {
      pages: [
        {
          likes_count: 0,
          is_liked: false,
          comments: [comments[0]],
          comments_count: 1,
        },
      ],
      pageParams: [0],
    })
    const user = userEvent.setup()
    const view = render(
      <QueryClientProvider client={client}>
        <NewsDetail />
      </QueryClientProvider>
    )
    try {
      const section = await screen.findByRole("region", { name: "news:sections.comments" })
      await within(section).findByText("Comment number 0")
      await user.type(
        within(section).getByRole("textbox", { name: "news:form.commentAriaLabel" }),
        "Draft"
      )
      await act(async () => {
        await client.invalidateQueries({ queryKey: ["news", fixture.newsId, "interactions"] })
      })
      expect(calls).toBe(1)
      expect(within(section).getByText("Comment number 0")).toBeVisible()
      expect(
        within(section).getByRole("textbox", { name: "news:form.commentAriaLabel" })
      ).toHaveValue("Draft")
      expect(within(section).queryByText("news:states.noComments")).not.toBeInTheDocument()
    } finally {
      view.unmount()
      client.clear()
    }
  })

  it.each([-1, Number.NaN, Number.POSITIVE_INFINITY, 1.5])(
    "falls back to the loaded comment count when the supplied total is %s",
    (commentsCount) => {
      render(
        <NewsComments
          comments={[comments[0]!]}
          commentsCount={commentsCount}
          isCommenting={false}
          addComment={() => {}}
          updateComment={() => {}}
          deleteComment={() => {}}
          t={(key) => key}
          getMoscowDate={() => "date"}
        />
      )
      const section = screen.getByRole("region", { name: "news:sections.comments" })
      expect(within(section).getByRole("heading").parentElement).toHaveTextContent("1")
    }
  )

  it.each(["authenticated", "anonymous"] as const)(
    "falls back to offsets when an older server ignores the cursor probe for an %s reader",
    async (mode) => {
      fixture.user =
        mode === "authenticated"
          ? {
              id: "019961d3-bb00-7000-8000-000000000010",
              full_name: "Comment Author",
              role: "student",
            }
          : null
      useAuthStore.setState({ user: fixture.user as UserState | null, loading: false })
      const requests: { offset: string | null; cursor: string | null }[] = []
      server.use(
        http.get(`*/news/${fixture.newsId}/interactions`, ({ request }) => {
          const params = new URL(request.url).searchParams
          const offset = params.get("offset")
          requests.push({ offset, cursor: params.get("cursor") })
          const start = Number(offset ?? 0)
          return HttpResponse.json({
            likes_count: 0,
            is_liked: false,
            comments: comments.slice(start, start + 20),
            comments_count: 23,
          })
        })
      )
      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      seedDetail(client, mode, 23)
      const user = userEvent.setup()
      const view = render(
        <QueryClientProvider client={client}>
          <NewsDetail />
        </QueryClientProvider>
      )
      try {
        const section = await screen.findByRole("region", { name: "news:sections.comments" })
        await within(section).findByText("Comment number 19")
        await user.click(screen.getByRole("button", { name: "news:actions.loadMoreComments" }))
        await within(section).findByText("Comment number 22")
        expect(screen.queryByRole("button", { name: "news:actions.loadMoreComments" })).toBeNull()
        expect(requests).toEqual([
          { offset: null, cursor: "start" },
          { offset: "20", cursor: null },
        ])
      } finally {
        view.unmount()
        client.clear()
      }
    }
  )

  it.each(["authenticated", "anonymous"] as const)(
    "traverses opaque comment cursors through an exactly full final page for an %s reader",
    async (mode) => {
      fixture.user =
        mode === "authenticated"
          ? {
              id: "019961d3-bb00-7000-8000-000000000010",
              full_name: "Comment Author",
              role: "student",
            }
          : null
      useAuthStore.setState({ user: fixture.user as UserState | null, loading: false })
      const requests: { offset: string | null; cursor: string | null; limit: string | null }[] = []
      const fetchSpy = vi.spyOn(globalThis, "fetch")
      server.use(
        http.get(`*/news/${fixture.newsId}/interactions`, ({ request }) => {
          const params = new URL(request.url).searchParams
          const offset = params.get("offset")
          const cursor = params.get("cursor")
          requests.push({ offset, cursor, limit: params.get("limit") })
          const page =
            cursor === cursorAfterFirst
              ? comments.slice(20, 40)
              : cursor === cursorAfterSecond || (offset !== null && offset !== "0")
                ? []
                : comments.slice(0, 20)
          const nextCursor =
            cursor === cursorAfterFirst
              ? cursorAfterSecond
              : cursor === "start"
                ? cursorAfterFirst
                : null
          return HttpResponse.json({
            likes_count: 0,
            is_liked: false,
            comments: page,
            comments_count: 40,
            next_cursor: nextCursor,
          })
        })
      )
      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      seedDetail(client, mode, 40)
      const user = userEvent.setup()
      const view = render(
        <QueryClientProvider client={client}>
          <NewsDetail />
        </QueryClientProvider>
      )
      try {
        const section = await screen.findByRole("region", { name: "news:sections.comments" })
        await within(section).findByText("Comment number 19")
        await user.click(screen.getByRole("button", { name: "news:actions.loadMoreComments" }))
        await within(section).findByText("Comment number 39", {}, { timeout: 4000 })
        await user.click(screen.getByRole("button", { name: "news:actions.loadMoreComments" }))
        await waitFor(() =>
          expect(screen.queryByRole("button", { name: "news:actions.loadMoreComments" })).toBeNull()
        )
        expect(requests).toEqual([
          { offset: null, cursor: "start", limit: "20" },
          { offset: null, cursor: cursorAfterFirst, limit: "20" },
          { offset: null, cursor: cursorAfterSecond, limit: "20" },
        ])
        for (const comment of comments.slice(0, 40)) {
          expect(within(section).getAllByText(comment.content)).toHaveLength(1)
        }
        if (mode === "anonymous") {
          const reads = fetchSpy.mock.calls.filter(([url]) =>
            String(url).includes(`/news/${fixture.newsId}/interactions`)
          )
          expect(reads.map(([, init]) => init?.credentials)).toEqual(["omit", "omit", "omit"])
        }
      } finally {
        view.unmount()
        client.clear()
        fetchSpy.mockRestore()
      }
    }
  )

  it.each(["post", "delete"] as const)(
    "uses the server cursor while an optimistic %s changes the visible page",
    async (action) => {
      fixture.user = {
        id: "019961d3-bb00-7000-8000-000000000010",
        full_name: "Comment Author",
        role: "student",
      }
      useAuthStore.setState({ user: fixture.user as UserState, loading: false })
      const pending = deferred()
      let mutationStarted = false
      const requestedCursors: (string | null)[] = []
      server.use(
        http.get(`*/news/${fixture.newsId}/interactions`, ({ request }) => {
          const params = new URL(request.url).searchParams
          const cursor = params.get("cursor")
          requestedCursors.push(cursor)
          const page =
            cursor === cursorAfterFirst
              ? comments.slice(20, 23)
              : cursor === "start" || params.get("offset") === "0"
                ? comments.slice(0, 20)
                : []
          return HttpResponse.json({
            likes_count: 0,
            is_liked: false,
            comments: page,
            comments_count: 23,
            next_cursor: cursor === "start" ? cursorAfterFirst : null,
          })
        }),
        http.post(`*/news/${fixture.newsId}/comment`, async () => {
          mutationStarted = true
          await pending.promise
          return HttpResponse.json({ ...comments[0], content: "Pending comment" })
        }),
        http.delete(`*/news/comments/${comments[19]!.id}`, async () => {
          mutationStarted = true
          await pending.promise
          return HttpResponse.json({ ok: true })
        })
      )
      const client = new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
      })
      seedDetail(client, "authenticated", 23)
      const user = userEvent.setup()
      const view = render(
        <QueryClientProvider client={client}>
          <NewsDetail />
        </QueryClientProvider>
      )
      try {
        const section = await screen.findByRole("region", { name: "news:sections.comments" })
        await within(section).findByText("Comment number 19")
        if (action === "post") {
          await user.type(
            within(section).getByRole("textbox", { name: "news:form.commentAriaLabel" }),
            "Pending comment"
          )
          await user.click(
            within(section).getByRole("button", { name: "news:actions.postComment" })
          )
          await within(section).findByText("Pending comment", { selector: "p" })
        } else {
          const row = within(section).getByText("Comment number 19").parentElement!
          await user.click(within(row).getByRole("button", { name: "news:actions.deleteComment" }))
          await user.click(screen.getByRole("button", { name: "common:buttons.delete" }))
          await waitFor(() => expect(within(section).queryByText("Comment number 19")).toBeNull())
        }
        await waitFor(() => expect(mutationStarted).toBe(true))
        await user.click(screen.getByRole("button", { name: "news:actions.loadMoreComments" }))
        await within(section).findByText("Comment number 22", {}, { timeout: 4000 })
        expect(requestedCursors).toEqual(["start", cursorAfterFirst])
        for (const comment of comments.slice(20, 23)) {
          expect(within(section).getAllByText(comment.content)).toHaveLength(1)
        }
      } finally {
        await act(async () => pending.resolve())
        await waitFor(() => expect(client.isMutating()).toBe(0))
        view.unmount()
        client.clear()
      }
    }
  )

  it("reports a cursor capability downgrade and retries without appending the repeated page", async () => {
    useAuthStore.setState({ user: null, loading: false })
    let downgrade = true
    const requestedCursors: (string | null)[] = []
    server.use(
      http.get(`*/news/${fixture.newsId}/interactions`, ({ request }) => {
        const params = new URL(request.url).searchParams
        const cursor = params.get("cursor")
        requestedCursors.push(cursor)
        if (cursor === cursorAfterFirst && downgrade) {
          return HttpResponse.json({
            likes_count: 0,
            is_liked: false,
            comments: comments.slice(0, 20),
            comments_count: 23,
          })
        }
        return HttpResponse.json({
          likes_count: 0,
          is_liked: false,
          comments:
            cursor === cursorAfterFirst
              ? comments.slice(20, 23)
              : cursor === "start" || params.get("offset") === "0"
                ? comments.slice(0, 20)
                : [],
          comments_count: 23,
          next_cursor: cursor === "start" ? cursorAfterFirst : null,
        })
      })
    )
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    seedDetail(client, "anonymous", 23)
    const user = userEvent.setup()
    const view = render(
      <QueryClientProvider client={client}>
        <NewsDetail />
      </QueryClientProvider>
    )
    try {
      const section = await screen.findByRole("region", { name: "news:sections.comments" })
      await within(section).findByText("Comment number 19")
      await user.click(screen.getByRole("button", { name: "news:actions.loadMoreComments" }))
      expect(await screen.findByRole("alert", {}, { timeout: 4000 })).toHaveTextContent(
        "news:states.commentsPageLoadError"
      )
      expect(within(section).getAllByText("Comment number 0")).toHaveLength(1)
      expect(within(section).queryByText("Comment number 20")).not.toBeInTheDocument()
      downgrade = false
      await user.click(screen.getByRole("button", { name: "news:actions.loadMoreComments" }))
      await within(section).findByText("Comment number 22")
      expect(screen.queryByRole("alert")).not.toBeInTheDocument()
      expect(requestedCursors).toEqual(["start", cursorAfterFirst, cursorAfterFirst])
    } finally {
      view.unmount()
      client.clear()
    }
  })

  it("rejects cursor capability loss after refreshing a legacy numeric cache", async () => {
    useAuthStore.setState({ user: null, loading: false })
    let downgrade = false
    const requests: { offset: string | null; cursor: string | null }[] = []
    server.use(
      http.get(`*/news/${fixture.newsId}/interactions`, ({ request }) => {
        const params = new URL(request.url).searchParams
        requests.push({ offset: params.get("offset"), cursor: params.get("cursor") })
        return HttpResponse.json({
          likes_count: 0,
          is_liked: false,
          comments: downgrade
            ? [{ ...comments[0], content: "Downgraded cached comment" }]
            : [comments[0]],
          comments_count: 23,
          ...(downgrade ? {} : { next_cursor: cursorAfterFirst }),
        })
      })
    )
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const queryKey = ["news", fixture.newsId, "anonymous-interactions"]
    seedDetail(client, "anonymous", 23)
    client.setQueryData(queryKey, {
      pages: [
        {
          likes_count: 0,
          is_liked: false,
          comments: [comments[0]],
          comments_count: 23,
        },
      ],
      pageParams: [0],
    })
    const view = render(
      <QueryClientProvider client={client}>
        <NewsDetail />
      </QueryClientProvider>
    )
    try {
      const section = await screen.findByRole("region", { name: "news:sections.comments" })
      await within(section).findByText("Comment number 0")
      await act(async () => {
        await client.invalidateQueries({ queryKey })
      })
      expect(requests).toEqual([{ offset: "0", cursor: null }])
      expect(client.getQueryState(queryKey)?.status).toBe("success")
      const upgraded = client.getQueryData(queryKey)
      expect(upgraded).toMatchObject({
        pages: [{ next_cursor: cursorAfterFirst }],
        pageParams: [0],
      })

      downgrade = true
      await act(async () => {
        await client.invalidateQueries({ queryKey })
      })
      expect(requests).toHaveLength(2)
      expect(client.getQueryState(queryKey)?.status).toBe("error")
      expect(client.getQueryData(queryKey)).toEqual(upgraded)
      expect(within(section).getByText("Comment number 0")).toBeVisible()
      expect(within(section).queryByText("Downgraded cached comment")).not.toBeInTheDocument()

      downgrade = false
      await act(async () => {
        await client.invalidateQueries({ queryKey })
      })
      expect(requests).toEqual(Array.from({ length: 3 }, () => ({ offset: "0", cursor: null })))
      expect(client.getQueryState(queryKey)?.status).toBe("success")
      expect(client.getQueryData(queryKey)).toEqual(upgraded)
    } finally {
      view.unmount()
      client.clear()
    }
  })
})
