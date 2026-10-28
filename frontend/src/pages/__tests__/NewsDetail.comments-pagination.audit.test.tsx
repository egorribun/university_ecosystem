import { QueryClient, QueryClientProvider, notifyManager } from "@tanstack/react-query"
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest"

import { NEWS_COMMENTS_PAGE_SIZE, type NewsComment } from "@/hooks/useNewsInteraction"
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
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))
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

const comments: NewsComment[] = Array.from({ length: NEWS_COMMENTS_PAGE_SIZE + 3 }, (_, index) => ({
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

describe("NewsDetail comment pagination", () => {
  it.each(["authenticated", "anonymous"] as const)(
    "loads and displays the next bounded comment page for an %s reader",
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
      const secondPage = deferred()
      const requests: { offset: number; limit: number }[] = []
      const fetchSpy = vi.spyOn(globalThis, "fetch")
      server.use(
        http.get(`*/news/${fixture.newsId}`, () =>
          HttpResponse.json({
            id: fixture.newsId,
            title: "Article",
            content: "Body",
            created_at: "2026-10-01T12:00:00Z",
            image_url_optimized: null,
            likes_count: 4,
            is_liked: mode === "authenticated",
            comments_count: comments.length,
          })
        ),
        http.get(`*/news/${fixture.newsId}/interactions`, async ({ request }) => {
          const params = new URL(request.url).searchParams
          const offset = Number(params.get("offset"))
          const limit = Number(params.get("limit"))
          requests.push({ offset, limit })
          if (offset > 0) await secondPage.promise
          return HttpResponse.json({
            likes_count: 4,
            is_liked: mode === "authenticated",
            comments: comments.slice(offset, offset + limit),
            comments_count: comments.length,
          })
        })
      )

      const client = new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
      })
      const user = userEvent.setup()
      const view = render(
        <QueryClientProvider client={client}>
          <NewsDetail />
        </QueryClientProvider>
      )

      try {
        const section = await screen.findByRole("region", { name: "news:sections.comments" })
        await within(section).findByText("Comment number 19")
        expect(within(section).queryByText("Comment number 20")).not.toBeInTheDocument()
        expect(requests.map(({ limit, offset }) => [limit, offset])).toEqual([[20, 0]])

        const loadMore = screen.getByRole("button", { name: "news:actions.loadMoreComments" })
        await user.click(loadMore)
        await waitFor(() => expect(requests).toHaveLength(2))
        expect(loadMore).toBeDisabled()
        expect(loadMore).toHaveAttribute("aria-busy", "true")
        expect(within(section).getByText("Comment number 0")).toBeVisible()

        await act(async () => secondPage.resolve())
        await within(section).findByText("Comment number 22")
        for (const comment of comments) {
          expect(within(section).getByText(comment.content)).toBeVisible()
        }
        expect(screen.queryByRole("button", { name: "news:actions.loadMoreComments" })).toBeNull()
        expect(requests.map(({ limit, offset }) => [limit, offset])).toEqual([
          [20, 0],
          [20, 20],
        ])
        if (mode === "anonymous") {
          expect(
            client
              .getQueryCache()
              .find({ queryKey: ["news", fixture.newsId, "anonymous-interactions"] })?.meta?.persist
          ).toBe(false)
          expect(client.getQueryData(["news", fixture.newsId, "interactions"])).toBeUndefined()
          const publicReads = fetchSpy.mock.calls.filter(([url]) =>
            String(url).includes(`/news/${fixture.newsId}/interactions`)
          )
          expect(publicReads).toHaveLength(2)
          expect(publicReads.map(([, init]) => init?.credentials)).toEqual(["omit", "omit"])
        }
      } finally {
        await act(async () => secondPage.resolve())
        view.unmount()
        client.clear()
      }
    }
  )

  it("loads the next server page without skipping a comment while a new comment is pending", async () => {
    fixture.user = {
      id: "019961d3-bb00-7000-8000-000000000010",
      full_name: "Comment Author",
      role: "student",
    }
    useAuthStore.setState({ user: fixture.user as UserState, loading: false })
    const post = deferred()
    const serverComments = [...comments]
    const offsets: number[] = []
    let postStarted = false
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
          comments_count: serverComments.length,
        })
      ),
      http.get(`*/news/${fixture.newsId}/interactions`, ({ request }) => {
        const params = new URL(request.url).searchParams
        const offset = Number(params.get("offset"))
        const limit = Number(params.get("limit"))
        offsets.push(offset)
        return HttpResponse.json({
          likes_count: 4,
          is_liked: false,
          comments: serverComments.slice(offset, offset + limit),
          comments_count: serverComments.length,
        })
      }),
      http.post(`*/news/${fixture.newsId}/comment`, async () => {
        postStarted = true
        await post.promise
        const created = {
          ...comments[0]!,
          id: "019961d3-bb00-7000-8000-000000000099",
          content: "New comment",
        }
        serverComments.push(created)
        return HttpResponse.json(created)
      })
    )

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const user = userEvent.setup()
    const view = render(
      <QueryClientProvider client={client}>
        <NewsDetail />
      </QueryClientProvider>
    )
    try {
      const section = await screen.findByRole("region", { name: "news:sections.comments" })
      await within(section).findByText("Comment number 19")
      await user.type(
        screen.getByRole("textbox", { name: "news:form.commentAriaLabel" }),
        "New comment"
      )
      await user.click(screen.getByRole("button", { name: "news:actions.postComment" }))
      await within(section).findByText("New comment", { selector: "p" })
      await waitFor(() => expect(postStarted).toBe(true))

      await user.click(screen.getByRole("button", { name: "news:actions.loadMoreComments" }))
      await waitFor(() => expect(offsets).toHaveLength(2), { timeout: 4000 })
      expect([...offsets]).toEqual([0, 20])
      await within(section).findByText("Comment number 22")
      for (const comment of comments) {
        expect(within(section).getAllByText(comment.content)).toHaveLength(1)
      }
      expect(within(section).getByText("New comment", { selector: "p" })).toBeVisible()

      await act(async () => post.resolve())
      await waitFor(() => expect(client.isMutating()).toBe(0))
      await waitFor(() => {
        const row = within(section).getByText("New comment", { selector: "p" }).parentElement!
        expect(within(row).getByRole("button", { name: "news:actions.editComment" })).toBeEnabled()
      })
    } finally {
      await act(async () => post.resolve())
      view.unmount()
      await waitFor(() => expect(client.isMutating()).toBe(0))
      client.clear()
    }
  })

  it("preserves the server offset while a comment deletion is pending", async () => {
    fixture.user = {
      id: "019961d3-bb00-7000-8000-000000000010",
      full_name: "Comment Author",
      role: "student",
    }
    useAuthStore.setState({ user: fixture.user as UserState, loading: false })
    const deletion = deferred()
    const serverComments = [...comments]
    const offsets: number[] = []
    let deleteStarted = false
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
          comments_count: serverComments.length,
        })
      ),
      http.get(`*/news/${fixture.newsId}/interactions`, ({ request }) => {
        const params = new URL(request.url).searchParams
        const offset = Number(params.get("offset"))
        const limit = Number(params.get("limit"))
        offsets.push(offset)
        return HttpResponse.json({
          likes_count: 4,
          is_liked: false,
          comments: serverComments.slice(offset, offset + limit),
          comments_count: serverComments.length,
        })
      }),
      http.delete(`*/news/comments/${comments[0]!.id}`, async () => {
        deleteStarted = true
        await deletion.promise
        serverComments.shift()
        return HttpResponse.json({ ok: true })
      })
    )
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const user = userEvent.setup()
    const view = render(
      <QueryClientProvider client={client}>
        <NewsDetail />
      </QueryClientProvider>
    )
    try {
      const section = await screen.findByRole("region", { name: "news:sections.comments" })
      await within(section).findByText("Comment number 19")
      const row = within(section).getByText("Comment number 0").parentElement!
      await user.click(within(row).getByRole("button", { name: "news:actions.deleteComment" }))
      await user.click(screen.getByRole("button", { name: "common:buttons.delete" }))
      await waitFor(() => expect(deleteStarted).toBe(true))
      await waitFor(() => expect(within(section).queryByText("Comment number 0")).toBeNull())

      await user.click(screen.getByRole("button", { name: "news:actions.loadMoreComments" }))
      await waitFor(() => expect(offsets).toHaveLength(2))
      expect([...offsets]).toEqual([0, 20])
      await within(section).findByText("Comment number 22")
      for (const comment of comments.slice(1)) {
        expect(within(section).getAllByText(comment.content)).toHaveLength(1)
      }
      await act(async () => deletion.resolve())
      await waitFor(() => expect(client.isMutating()).toBe(0))
    } finally {
      await act(async () => deletion.resolve())
      view.unmount()
      await waitFor(() => expect(client.isMutating()).toBe(0))
      client.clear()
    }
  })

  it("uses the previous page format when reading an existing account cache", async () => {
    fixture.user = {
      id: "019961d3-bb00-7000-8000-000000000010",
      full_name: "Comment Author",
      role: "student",
    }
    useAuthStore.setState({ user: fixture.user as UserState, loading: false })
    const offsets: number[] = []
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
        return HttpResponse.json({
          likes_count: 4,
          is_liked: false,
          comments: comments.slice(offset, offset + limit),
          comments_count: comments.length,
        })
      })
    )
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    client.setQueryData(["news", fixture.newsId, "interactions"], {
      pages: [
        {
          likes_count: 4,
          is_liked: false,
          comments: [
            ...comments.slice(0, NEWS_COMMENTS_PAGE_SIZE),
            { ...comments[0]!, id: "optimistic-existing", content: "Pending cached comment" },
          ],
          comments_count: comments.length + 1,
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
      await screen.findByText("Pending cached comment")
      await user.click(screen.getByRole("button", { name: "news:actions.loadMoreComments" }))
      await screen.findByText("Comment number 22")
      expect(offsets).toEqual([20])
      expect(screen.getByText("Comment number 20")).toBeVisible()
    } finally {
      view.unmount()
      client.clear()
    }
  })
})
