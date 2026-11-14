type _MockedModuleType1 = typeof import("@/hooks/useShare")
import { QueryClient, QueryClientProvider, notifyManager } from "@tanstack/react-query"
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { http, HttpResponse } from "msw"
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest"

import { acceptBrowserSessionGeneration, invalidateSessionEpoch } from "@/stores/sessionEpoch"
import { useAuthStore } from "@/stores/useAuthStore"
import { server } from "@/tests/mocks/server"
import type { UserState } from "@/types/Auth"
import NewsDetail from "../NewsDetail"

const fixture = vi.hoisted(() => ({
  language: "en",
  newsId: "019961d3-bb00-7000-8000-000000000020",
  user: null as { id: string; full_name: string; role: "student" } | null,
}))

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => vi.fn(),
  useParams: () => ({ id: fixture.newsId }),
}))
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: fixture.user }) }))
vi.mock("@/contexts/LanguageContext", () => ({
  useLanguage: () => ({ language: fixture.language }),
}))
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => {
      if (key === "common:errorBoundary.retry")
        return fixture.language === "en" ? "Try again" : "Попробовать снова"
      return key
    },
  }),
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
  ...(await importOriginal<_MockedModuleType1>()),
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
vi.mock("@/components/news/NewsDetailBody", () => ({
  NewsDetailBody: () => <h1>Recovered article</h1>,
}))
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

vi.mock("@/hooks/useNewsInteraction", () => ({ useNewsInteraction: () => ({}) }))
vi.mock("@/components/news/NewsComments", () => ({ NewsComments: () => null }))

beforeAll(() => notifyManager.setNotifyFunction((callback) => act(callback)))
afterAll(() => notifyManager.setNotifyFunction((callback) => callback()))
beforeEach(() => {
  acceptBrowserSessionGeneration()
  invalidateSessionEpoch()
  fixture.user = null
  useAuthStore.setState({ user: null, loading: false })
})
afterEach(() => {
  cleanup()
  useAuthStore.setState({ user: null, loading: true })
})

const article = {
  id: fixture.newsId,
  title: "Article",
  content: "Body",
  created_at: "2026-10-01T12:00:00Z",
  image_url_optimized: null,
  likes_count: 0,
  is_liked: false,
  comments_count: 0,
}
function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retryDelay: 0 } } })
  const view = render(
    <QueryClientProvider client={client}>
      <NewsDetail />
    </QueryClientProvider>
  )
  return { client, ...view }
}

describe("NewsDetail real HTTP recovery", () => {
  it.each([
    ["ru", "anonymous"],
    ["en", "anonymous"],
    ["ru", "authenticated"],
    ["en", "authenticated"],
  ])("recovers after persistent 500 and repeated retry in %s for %s", async (language, mode) => {
    fixture.language = language
    fixture.user =
      mode === "authenticated"
        ? { id: "019961d3-bb00-7000-8000-000000000010", full_name: "Reader", role: "student" }
        : null
    useAuthStore.setState({ user: fixture.user as UserState | null, loading: false })
    let requests = 0
    let success = false
    let release!: () => void
    let pending: Promise<void> | undefined
    server.use(
      http.get(`*/news/${fixture.newsId}`, async () => {
        requests++
        await pending
        return success
          ? HttpResponse.json(article)
          : HttpResponse.json(
              {
                detail: "PRIVATE_PROBLEM_DETAIL https://private.example.test/?token=DO_NOT_REFLECT",
              },
              { status: 500 }
            )
      })
    )
    const view = mount()
    const label = language === "en" ? "Try again" : "Попробовать снова"
    try {
      const retry = await screen.findByRole("button", { name: label })
      expect(requests).toBe(2) // Existing retry:1 policy is retained.
      fireEvent.click(retry)
      await waitFor(() => expect(requests).toBe(4))
      const next = await screen.findByRole("button", { name: label })
      pending = new Promise<void>((resolve) => {
        release = resolve
      })
      success = true
      fireEvent.click(next)
      fireEvent.click(next)
      await waitFor(() => expect(requests).toBe(5))
      expect(screen.queryByRole("button", { name: label })).not.toBeInTheDocument()
      await act(async () => release())
      expect(await screen.findByRole("heading", { name: "Recovered article" })).toBeVisible()
      expect(requests).toBe(5)
    } finally {
      view.unmount()
      view.client.clear()
    }
  })
  it("leaves a missing article distinct from a retryable server failure", async () => {
    server.use(http.get(`*/news/${fixture.newsId}`, () => new HttpResponse(null, { status: 404 })))
    const view = mount()
    try {
      await screen.findByText("news:states.loadError")
      expect(
        screen.queryByRole("button", { name: /Try again|Попробовать снова/u })
      ).not.toBeInTheDocument()
      expect(screen.getByRole("button", { name: "common:buttons.back" })).toBeEnabled()
    } finally {
      view.unmount()
      view.client.clear()
    }
  })
  it("does not restore an old error page after navigation away during retry", async () => {
    let recover = false
    let release!: () => void
    const pending = new Promise<void>((resolve) => {
      release = resolve
    })
    server.use(
      http.get(`*/news/${fixture.newsId}`, async () => {
        if (!recover) return new HttpResponse(null, { status: 500 })
        await pending
        return HttpResponse.json(article)
      })
    )
    const view = mount()
    try {
      const retry = await screen.findByRole("button", { name: /Try again|Попробовать снова/u })
      recover = true
      fireEvent.click(retry)
      view.rerender(<h1>Another page</h1>)
      await act(async () => release())
      expect(screen.getByRole("heading", { name: "Another page" })).toBeVisible()
      expect(screen.queryByText("Recovered article")).not.toBeInTheDocument()
    } finally {
      view.unmount()
      view.client.clear()
    }
  })
})
