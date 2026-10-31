import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, renderHook, waitFor } from "@testing-library/react"
import { type PropsWithChildren } from "react"
import { describe, expect, it, vi } from "vitest"
import { newsListQueryKey, useAnonymousReadMode } from "@/api/hooks/news"
import { type NewsItem } from "@/api/news"
import { acceptBrowserSessionGeneration, getBrowserSessionGeneration } from "@/stores/sessionEpoch"
import { renderToStaticMarkup } from "react-dom/server"
import { useArticleNavigation } from "../useArticleNavigation"

const makeArticle = (id: string, title: string) => ({ id, title }) as unknown as NewsItem

const makeClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  })

const makeWrapper = (queryClient: QueryClient) => {
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  return Wrapper
}

const articleListKey = newsListQueryKey({ language: "en", limit: 12 })

function ServerNavigationProbe() {
  const navigation = useArticleNavigation("current")
  return (
    <output>
      {navigation.prevId ?? "none"}|{navigation.nextId ?? "none"}
    </output>
  )
}

describe("useArticleNavigation", () => {
  it("returns empty navigation when the current article is absent from cached pages", () => {
    const queryClient = makeClient()
    const { result } = renderHook(() => useArticleNavigation("missing"), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current).toEqual({ prevId: null, nextId: null, prevTitle: null, nextTitle: null })
  })

  it("flattens cached pages, deduplicates IDs, and finds adjacent articles in order", () => {
    const queryClient = makeClient()
    queryClient.setQueryData(newsListQueryKey({ language: "en", limit: 12 }), {
      pages: [
        {
          items: [makeArticle("first", "First"), makeArticle("current", "Current")],
        },
      ],
    })
    queryClient.setQueryData(newsListQueryKey({ language: "ru", limit: 12 }), {
      pages: [
        {
          items: [makeArticle("current", "Duplicate"), makeArticle("last", "Last")],
        },
      ],
    })

    const { result } = renderHook(() => useArticleNavigation("current"), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current).toEqual({
      prevId: "first",
      nextId: "last",
      prevTitle: "First",
      nextTitle: "Last",
    })
  })

  it("handles missing page data and first/last navigation boundaries", () => {
    const queryClient = makeClient()
    queryClient.setQueryData(newsListQueryKey({ language: "en", limit: 12 }), {})
    expect(
      renderHook(() => useArticleNavigation("missing"), {
        wrapper: makeWrapper(queryClient),
      }).result.current
    ).toEqual({ prevId: null, nextId: null, prevTitle: null, nextTitle: null })

    act(() => {
      queryClient.setQueryData(newsListQueryKey({ language: "ru", limit: 12 }), {
        pages: [{}, { items: undefined }],
      })
    })
    expect(
      renderHook(() => useArticleNavigation("missing"), {
        wrapper: makeWrapper(queryClient),
      }).result.current
    ).toEqual({ prevId: null, nextId: null, prevTitle: null, nextTitle: null })

    act(() => {
      queryClient.setQueryData(newsListQueryKey({ language: "de", limit: 12 }), {
        pages: [
          {
            items: [makeArticle("first", "First"), makeArticle("last", "Last")],
          },
        ],
      })
    })
    expect(
      renderHook(() => useArticleNavigation("first"), {
        wrapper: makeWrapper(queryClient),
      }).result.current
    ).toEqual({ prevId: null, nextId: "last", prevTitle: null, nextTitle: "Last" })
    expect(
      renderHook(() => useArticleNavigation("last"), {
        wrapper: makeWrapper(queryClient),
      }).result.current
    ).toEqual({ prevId: "first", nextId: null, prevTitle: "First", nextTitle: null })
  })

  it("ignores cache updates outside the news-list queries", () => {
    const queryClient = makeClient()
    let renderCount = 0
    const { result } = renderHook(
      () => {
        renderCount += 1
        return useArticleNavigation("current")
      },
      { wrapper: makeWrapper(queryClient) }
    )
    const initialRenderCount = renderCount

    act(() => {
      queryClient.setQueryData(["users", "me"], {
        pages: [
          { items: [makeArticle("previous", "Previous"), makeArticle("current", "Current")] },
        ],
      })
    })

    expect(renderCount).toBe(initialRenderCount)
    expect(result.current).toEqual({ prevId: null, nextId: null, prevTitle: null, nextTitle: null })
  })
  it("hides cached neighbors when a remote session change rerenders the reader", () => {
    const generationKey = "ecosystem.session.generation.v1"
    const originalGeneration = window.localStorage.getItem(generationKey)
    acceptBrowserSessionGeneration()
    const staleNonce =
      getBrowserSessionGeneration() === "aud441-stale-generation"
        ? "aud441-stale-generation-2"
        : "aud441-stale-generation"
    const queryClient = makeClient()
    queryClient.setQueryData(articleListKey, {
      pages: [
        {
          items: [
            makeArticle("previous", "Previous"),
            makeArticle("current", "Current"),
            makeArticle("next", "Next"),
          ],
        },
      ],
    })
    let unmount: (() => void) | undefined

    try {
      const hook = renderHook(
        () => {
          useAnonymousReadMode()
          return useArticleNavigation("current")
        },
        { wrapper: makeWrapper(queryClient) }
      )
      unmount = hook.unmount
      expect(hook.result.current).toEqual({
        prevId: "previous",
        nextId: "next",
        prevTitle: "Previous",
        nextTitle: "Next",
      })

      window.localStorage.setItem(generationKey, JSON.stringify({ nonce: staleNonce, hash: null }))
      act(() => {
        window.dispatchEvent(new StorageEvent("storage", { key: generationKey }))
      })

      expect(hook.result.current).toEqual({
        prevId: null,
        nextId: null,
        prevTitle: null,
        nextTitle: null,
      })
    } finally {
      unmount?.()
      if (originalGeneration === null) {
        window.localStorage.removeItem(generationKey)
      } else {
        window.localStorage.setItem(generationKey, originalGeneration)
      }
      acceptBrowserSessionGeneration()
    }
  })

  it("uses the QueryClient cache through the server snapshot when window is absent", () => {
    const queryClient = makeClient()
    queryClient.setQueryData(articleListKey, {
      pages: [
        {
          items: [
            makeArticle("previous", "Previous"),
            makeArticle("current", "Current"),
            makeArticle("next", "Next"),
          ],
        },
      ],
    })

    vi.stubGlobal("window", undefined)
    try {
      const markup = renderToStaticMarkup(
        <QueryClientProvider client={queryClient}>
          <ServerNavigationProbe />
        </QueryClientProvider>
      )

      expect(markup).toBe("<output>previous|next</output>")
    } finally {
      vi.unstubAllGlobals()
    }
  })
  it("updates neighbors when news-list data arrives and changes after render", async () => {
    const queryClient = makeClient()
    const { result } = renderHook(() => useArticleNavigation("current"), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current).toEqual({ prevId: null, nextId: null, prevTitle: null, nextTitle: null })

    act(() => {
      queryClient.setQueryData(articleListKey, {
        pages: [
          { items: [makeArticle("previous", "Previous"), makeArticle("current", "Current")] },
        ],
      })
    })

    await waitFor(() => {
      expect(result.current).toEqual({
        prevId: "previous",
        nextId: null,
        prevTitle: "Previous",
        nextTitle: null,
      })
    })

    act(() => {
      queryClient.setQueryData(articleListKey, {
        pages: [
          {
            items: [
              makeArticle("previous", "Previous"),
              makeArticle("current", "Current"),
              makeArticle("next", "Next"),
            ],
          },
        ],
      })
    })

    await waitFor(() => {
      expect(result.current).toEqual({
        prevId: "previous",
        nextId: "next",
        prevTitle: "Previous",
        nextTitle: "Next",
      })
    })
  })
})
