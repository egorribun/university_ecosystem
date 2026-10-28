import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { invalidateSessionEpoch } from "@/stores/sessionEpoch"

type InteractionState = {
  likes_count: number
  comments_count: number
  is_liked: boolean
}

const mocks = vi.hoisted(() => {
  let currentUser: { role: string } | null = null
  const authListeners = new Set<() => void>()

  return {
    get user() {
      return currentUser
    },
    set user(value: { role: string } | null) {
      currentUser = value
      authListeners.forEach((listener) => listener())
    },
    subscribeAuth(listener: () => void) {
      authListeners.add(listener)
      return () => {
        authListeners.delete(listener)
      }
    },
    getAuthSnapshot() {
      return currentUser
    },
    language: "en",
    translationNamespaces: [] as unknown[],
    interactions: undefined as InteractionState | undefined,
    toggleLike: vi.fn(),
    isBookmarked: vi.fn(() => false),
    toggleBookmark: vi.fn(),
    deleteNews: vi.fn(),
    fetchNewsItem: vi.fn(),
    onChange: vi.fn(),
    sanitizeNewsText: vi.fn(async (value: string) => `sanitized:${value}`),
    viewRender: vi.fn(),
    interactionArgs: [] as unknown[][],
  }
})

vi.mock("@/contexts/AuthContext", async () => {
  const { useSyncExternalStore } = await import("react")

  return {
    useAuth: () => ({
      user: useSyncExternalStore(mocks.subscribeAuth, mocks.getAuthSnapshot, mocks.getAuthSnapshot),
    }),
  }
})

vi.mock("@/contexts/LanguageContext", () => ({
  useLanguage: () => ({ language: mocks.language }),
}))

vi.mock("@/hooks/useNewsInteraction", () => ({
  useNewsInteraction: (...args: unknown[]) => {
    mocks.interactionArgs.push(args)
    return { interactions: mocks.interactions, toggleLikeAsync: mocks.toggleLike }
  },
}))

vi.mock("@/hooks/useBookmarks", () => ({
  useBookmarks: () => ({
    isBookmarked: mocks.isBookmarked,
    toggleBookmark: mocks.toggleBookmark,
  }),
}))

vi.mock("@/components/ui/Spotlight", () => ({
  useSpotlight: () => ({ mouseX: {}, mouseY: {}, onMouseMove: vi.fn() }),
}))

vi.mock("@/utils/sanitize", () => ({
  sanitizeNewsText: mocks.sanitizeNewsText,
}))

vi.mock("@/utils/localize", () => ({
  localizeField: (value: string, _english: string | null | undefined, language: string) =>
    `${language}:${value}`,
}))

vi.mock("@/features/news/categories", () => ({
  inferNewsCategory: (item: {
    title: string
    content: string
    title_en?: string | null
    content_en?: string | null
  }) => {
    const title = item.title_en?.trim() ? item.title_en : item.title
    const content = item.content_en?.trim() ? item.content_en : item.content
    return `category:${title}|${content}`
  },
}))

vi.mock("@/utils/readingTime", () => ({
  estimateReadingTime: (content: string) => content.length,
}))

vi.mock("@/api/client", () => ({
  default: { delete: mocks.deleteNews },
}))

vi.mock("@/api/news", () => ({ fetchNewsItem: mocks.fetchNewsItem }))

vi.mock("react-i18next", () => ({
  useTranslation: (namespaces?: unknown) => {
    mocks.translationNamespaces.push(namespaces)
    return { t: (key: string) => key }
  },
}))

vi.mock("@/components/news/NewsCardView", () => ({
  NewsCardView: (props: {
    id: string
    editTargetId?: string
    title: string
    previewText: string
    isAdmin: boolean
    isLiked: boolean
    likesCount: number
    commentsCount: number
    isBookmarked: boolean
    editOpen: boolean
    confirmDeleteOpen: boolean
    onToggleLike: () => void
    onToggleBookmark: () => void
    onEditOpen: () => void
    onEditClose: () => void
    onDeleteOpen: () => void
    onDeleteClose: () => void
    onDeleteConfirm: () => void
    onEditSuccess: () => void
    onErrorClose: () => void
    error: string
    loading: boolean
    editData: {
      title: string
      content: string
      title_en: string
      content_en: string
      image_url: string
    }
    t: {
      deleteTitle: string
      deleteDesc: string
      confirm: string
      cancel: string
    }
    priority?: boolean
  }) => {
    mocks.viewRender(props)
    return (
      <div data-testid="news-card-view">
        <span data-testid="card-title">{props.title}</span>
        <span data-testid="card-preview">{props.previewText}</span>
        <span data-testid="card-stats">
          {props.isLiked ? "liked" : "not-liked"}:{props.likesCount}:{props.commentsCount}:
          {props.isBookmarked ? "bookmarked" : "not-bookmarked"}
        </span>
        <button type="button" onClick={props.onToggleLike}>
          toggle like
        </button>
        <button type="button" onClick={props.onToggleBookmark}>
          toggle bookmark
        </button>
        {props.isAdmin && (
          <button type="button" onClick={props.onEditOpen}>
            open edit
          </button>
        )}
        {props.editOpen && (
          <div role="dialog">
            <button type="button" onClick={props.onEditClose}>
              close edit
            </button>
            <button type="button" onClick={props.onEditSuccess}>
              edit success
            </button>
          </div>
        )}
        {props.isAdmin && (
          <button type="button" onClick={props.onDeleteOpen}>
            open delete
          </button>
        )}
        {props.confirmDeleteOpen && (
          <div role="alertdialog">
            <button type="button" onClick={props.onDeleteConfirm}>
              confirm delete
            </button>
            <button type="button" onClick={props.onDeleteClose}>
              close delete
            </button>
          </div>
        )}
        {props.error && (
          <div role="status">
            <span>{props.error}</span>
            <button type="button" onClick={props.onErrorClose}>
              close error
            </button>
          </div>
        )}
      </div>
    )
  },
}))

import NewsCard, { type NewsCardProps } from "@/components/news/NewsCard"

const baseProps = {
  id: "news-1",
  title: "Campus update",
  content: "The campus library is open.",
  title_en: "Campus update",
  content_en: "The campus library is open.",
  created_at: "2026-08-03T12:00:00Z",
  image_url: "/news.png",
  likes_count: 4,
  comments_count: 2,
  is_liked: false,
  priority: true,
}

beforeEach(() => {
  mocks.user = null
  mocks.language = "en"
  mocks.translationNamespaces.length = 0
  mocks.interactionArgs.length = 0
  mocks.interactions = { likes_count: 9, comments_count: 8, is_liked: true }
  mocks.deleteNews.mockResolvedValue(undefined)
  vi.clearAllMocks()
  mocks.deleteNews.mockResolvedValue(undefined)
  mocks.fetchNewsItem.mockResolvedValue({
    status: 200,
    data: {
      id: "news-1",
      title: "Русский оригинал",
      content: "Текст на русском языке.",
      title_en: "English source title",
      content_en: "English source body.",
      image_url: "/news-source.png",
    },
  })
  mocks.isBookmarked.mockReturnValue(false)
  mocks.sanitizeNewsText.mockImplementation(async (value: string) => `sanitized:${value}`)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("NewsCard — state orchestration", () => {
  it("does not show a late like failure after the session changes", async () => {
    let reject!: (error: Error) => void
    mocks.toggleLike.mockReturnValueOnce(
      new Promise((_resolve, fail) => {
        reject = fail
      })
    )
    render(<NewsCard {...baseProps} />)
    fireEvent.click(await screen.findByRole("button", { name: "toggle like" }))
    invalidateSessionEpoch()
    await act(async () => reject(new Error("Network Error")))
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
  })
  it("reports a like request whose outcome could not be confirmed", async () => {
    mocks.toggleLike.mockRejectedValueOnce(new Error("Network Error"))
    render(<NewsCard {...baseProps} />)
    fireEvent.click(await screen.findByRole("button", { name: "toggle like" }))
    expect(await screen.findByRole("status")).toHaveTextContent(
      "news:notifications.interactionError"
    )
  })
  it("localizes and sanitizes content, forwards interactions, and falls back to initial stats", async () => {
    mocks.interactions = undefined
    const { rerender } = render(<NewsCard {...baseProps} onChange={mocks.onChange} />)
    rerender(<NewsCard {...baseProps} onChange={mocks.onChange} />)

    await waitFor(() => expect(screen.getByTestId("card-preview")).toHaveTextContent("sanitized:"))
    expect(mocks.translationNamespaces.at(-1)).toEqual(["news", "common"])
    expect(screen.getByTestId("card-title")).toHaveTextContent("en:Campus update")
    expect(screen.getByTestId("card-stats")).toHaveTextContent("not-liked:4:2:not-bookmarked")
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument()
    expect(screen.queryByRole("status")).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "toggle like" }))
    fireEvent.click(screen.getByRole("button", { name: "toggle bookmark" }))
    expect(mocks.toggleLike).toHaveBeenCalledOnce()
    expect(mocks.toggleBookmark).toHaveBeenCalledWith("news-1")
  })

  it("uses interaction data when available and keeps bookmark callbacks bound to the current id", async () => {
    const { rerender } = render(<NewsCard {...baseProps} onChange={mocks.onChange} />)

    await waitFor(() => expect(screen.getByTestId("card-stats")).toHaveTextContent("liked:9:8"))

    mocks.toggleBookmark.mockClear()
    rerender(<NewsCard {...baseProps} id="news-2" onChange={mocks.onChange} />)
    await waitFor(() => expect(screen.getByTestId("card-stats")).toHaveTextContent("liked:9:8"))
    fireEvent.click(screen.getByRole("button", { name: "toggle bookmark" }))

    expect(mocks.toggleBookmark).toHaveBeenCalledWith("news-2")
  })

  it("forwards normalized edit data, dialog translations, and default interaction state", async () => {
    mocks.user = { role: "admin" }
    mocks.interactions = undefined
    render(
      <NewsCard
        {...baseProps}
        title_en={null}
        content_en={null}
        image_url={undefined}
        likes_count={undefined}
        comments_count={undefined}
        is_liked={undefined}
        priority={undefined}
      />
    )

    await waitFor(() => expect(mocks.viewRender).toHaveBeenCalled())
    const props = mocks.viewRender.mock.calls.at(-1)?.[0] as {
      editData: Record<string, string>
      t: Record<string, string>
      isLiked: boolean
      likesCount: number
      commentsCount: number
      priority?: boolean
    }

    expect(props.editData).toEqual({
      title: "Campus update",
      content: "The campus library is open.",
      title_en: "",
      content_en: "",
      image_url: "",
    })
    expect(props.t).toEqual({
      deleteTitle: "news:dialogs.delete.title",
      deleteDesc: "news:dialogs.delete.description",
      confirm: "common:buttons.delete",
      cancel: "common:buttons.cancel",
    })
    expect(props.isLiked).toBe(false)
    expect(props.likesCount).toBe(0)
    expect(props.commentsCount).toBe(0)
    expect(props.priority).toBeUndefined()
  })

  it("keeps the loading state visible until an asynchronous delete settles", async () => {
    mocks.user = { role: "admin" }
    let resolveDelete!: () => void
    mocks.deleteNews.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolveDelete = resolve
        })
    )
    render(<NewsCard {...baseProps} onChange={mocks.onChange} />)

    await waitFor(() => expect(mocks.viewRender).toHaveBeenCalled())
    fireEvent.click(screen.getByRole("button", { name: "open delete" }))
    fireEvent.click(screen.getByRole("button", { name: "confirm delete" }))

    await waitFor(() => {
      const props = mocks.viewRender.mock.calls.at(-1)?.[0] as { loading: boolean }
      expect(props.loading).toBe(true)
    })
    resolveDelete()
    await waitFor(() => {
      const props = mocks.viewRender.mock.calls.at(-1)?.[0] as {
        loading: boolean
        confirmDeleteOpen: boolean
      }
      expect(props.loading).toBe(false)
      expect(props.confirmDeleteOpen).toBe(false)
    })
  })

  it("rerenders when identity props change but ignores interaction counters", async () => {
    const onChange = vi.fn()
    const { rerender } = render(<NewsCard {...baseProps} onChange={onChange} />)
    await waitFor(() => expect(mocks.viewRender).toHaveBeenCalled())

    const identityChanges: Array<[string, unknown]> = [
      ["id", "news-2"],
      ["title", "A new title"],
      ["title_en", "A new English title"],
      ["content", "A new body"],
      ["content_en", "A new English body"],
      ["created_at", "2026-08-04T12:00:00Z"],
      ["image_url", "/new-image.png"],
      ["onChange", vi.fn()],
      ["priority", false],
    ]

    for (const [key, value] of identityChanges) {
      const before = mocks.viewRender.mock.calls.length
      const changedProps = { ...baseProps, onChange, [key]: value } as NewsCardProps
      rerender(<NewsCard {...changedProps} />)
      await waitFor(() => expect(mocks.viewRender.mock.calls.length).toBeGreaterThan(before))

      const changed = mocks.viewRender.mock.calls.length
      rerender(<NewsCard {...baseProps} onChange={onChange} />)
      await waitFor(() => expect(mocks.viewRender.mock.calls.length).toBeGreaterThan(changed))
    }

    const beforeCounters = mocks.viewRender.mock.calls.length
    rerender(
      <NewsCard {...baseProps} onChange={onChange} likes_count={99} comments_count={77} is_liked />
    )
    await Promise.resolve()
    expect(mocks.viewRender.mock.calls.length).toBe(beforeCounters)
  })

  it("handles successful admin delete and edit callbacks", async () => {
    mocks.user = { role: "admin" }
    render(<NewsCard {...baseProps} onChange={mocks.onChange} />)

    fireEvent.click(screen.getByRole("button", { name: "open edit" }))
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument())
    fireEvent.click(screen.getByRole("button", { name: "edit success" }))
    fireEvent.click(screen.getByRole("button", { name: "close edit" }))
    expect(mocks.onChange).toHaveBeenCalledOnce()

    fireEvent.click(screen.getByRole("button", { name: "open delete" }))
    fireEvent.click(screen.getByRole("button", { name: "close delete" }))
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "open delete" }))
    fireEvent.click(screen.getByRole("button", { name: "confirm delete" }))
    await waitFor(() => expect(mocks.deleteNews).toHaveBeenCalledWith("/news/news-1"))
    expect(mocks.onChange).toHaveBeenCalledTimes(2)
  })

  it("loads Russian source fields before opening the English editor", async () => {
    mocks.user = { role: "admin" }
    render(
      <NewsCard {...baseProps} title="Localized English title" content="Localized English body." />
    )

    await waitFor(() => expect(mocks.viewRender).toHaveBeenCalled())
    fireEvent.click(screen.getByRole("button", { name: "open edit" }))
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument())

    expect(mocks.fetchNewsItem).toHaveBeenCalledWith(
      "news-1",
      expect.objectContaining({ language: "ru", signal: expect.any(AbortSignal) })
    )
    const props = mocks.viewRender.mock.calls.at(-1)?.[0] as {
      editData: Record<string, string>
    }
    expect(props.editData).toEqual({
      title: "Русский оригинал",
      content: "Текст на русском языке.",
      title_en: "English source title",
      content_en: "English source body.",
      image_url: "/news-source.png",
    })
  })

  it("keeps an open edit session bound to its original article and data", async () => {
    mocks.user = { role: "admin" }
    const { rerender } = render(<NewsCard {...baseProps} />)

    fireEvent.click(screen.getByRole("button", { name: "open edit" }))
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument())
    const original = mocks.viewRender.mock.calls.at(-1)?.[0] as {
      id: string
      editTargetId?: string
      editOpen: boolean
      editData: Record<string, string>
    }
    expect(original.editTargetId).toBe("news-1")
    expect(original.editData.title).toBe("Русский оригинал")

    mocks.language = "ru"
    rerender(<NewsCard {...baseProps} />)
    const localeChanged = mocks.viewRender.mock.calls.at(-1)?.[0] as typeof original
    expect(localeChanged.editOpen).toBe(true)
    expect(localeChanged.editTargetId).toBe("news-1")
    expect(localeChanged.editData).toEqual(original.editData)

    rerender(
      <NewsCard
        {...baseProps}
        id="news-2"
        title="Different article"
        content="Different article body"
        image_url="/different.png"
      />
    )

    const retained = mocks.viewRender.mock.calls.at(-1)?.[0] as typeof original
    expect(retained.id).toBe("news-2")
    expect(retained.editOpen).toBe(true)
    expect(retained.editTargetId).toBe("news-1")
    expect(retained.editData).toEqual(original.editData)
    expect(screen.getByRole("dialog")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "close edit" }))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "open edit" }))
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument())

    const next = mocks.viewRender.mock.calls.at(-1)?.[0] as typeof original
    expect(next.editOpen).toBe(true)
    expect(next.editTargetId).toBe("news-2")
    expect(next.editData).toMatchObject({
      title: "Different article",
      content: "Different article body",
      image_url: "/different.png",
    })
  })

  it("closes an edit session immediately when admin access is lost", async () => {
    mocks.user = { role: "admin" }
    render(<NewsCard {...baseProps} />)
    fireEvent.click(screen.getByRole("button", { name: "open edit" }))
    expect(await screen.findByRole("dialog")).toBeInTheDocument()

    act(() => {
      mocks.user = null
    })

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "open edit" })).not.toBeInTheDocument()
    const currentView = mocks.viewRender.mock.calls.at(-1)?.[0] as {
      isAdmin: boolean
      editOpen: boolean
      onEditOpen: () => void
    }
    expect(currentView.isAdmin).toBe(false)
    expect(currentView.editOpen).toBe(false)

    act(() => {
      currentView.onEditOpen()
    })
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(mocks.viewRender.mock.calls.at(-1)?.[0].editOpen).toBe(false)
  })

  it("coalesces English source requests and ignores a late locale response", async () => {
    mocks.user = { role: "admin" }
    let resolveSource!: (value: { status: number; data: Record<string, string> }) => void
    mocks.fetchNewsItem.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveSource = resolve
      })
    )
    const { rerender } = render(<NewsCard {...baseProps} />)

    const openButton = screen.getByRole("button", { name: "open edit" })
    fireEvent.click(openButton)
    fireEvent.click(openButton)
    expect(mocks.fetchNewsItem).toHaveBeenCalledOnce()
    const options = mocks.fetchNewsItem.mock.calls[0]?.[1] as {
      language: string
      signal: AbortSignal
    }
    expect(options.language).toBe("ru")
    expect(options.signal).toBeInstanceOf(AbortSignal)

    mocks.language = "ru"
    rerender(<NewsCard {...baseProps} onChange={() => undefined} />)
    expect(options.signal.aborted).toBe(true)

    await act(async () => {
      resolveSource({
        status: 200,
        data: {
          id: "news-1",
          title: "Stale Russian title",
          content: "Stale Russian body",
          title_en: "Stale English title",
          content_en: "Stale English body",
          image_url: "/stale.png",
        },
      })
    })

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(mocks.viewRender.mock.calls.at(-1)?.[0].editOpen).toBe(false)
    fireEvent.click(screen.getByRole("button", { name: "open edit" }))
    expect(await screen.findByRole("dialog")).toBeInTheDocument()
    expect(mocks.fetchNewsItem).toHaveBeenCalledOnce()
    expect(mocks.viewRender.mock.calls.at(-1)?.[0].editData.title).toBe(baseProps.title)
  })

  it("keeps a replacement source request active when an aborted request rejects late", async () => {
    mocks.user = { role: "admin" }
    let rejectFirst!: (reason: unknown) => void
    let resolveSecond!: (value: { status: number; data: Record<string, unknown> }) => void
    mocks.fetchNewsItem.mockReset()
    mocks.fetchNewsItem
      .mockImplementationOnce(
        () =>
          new Promise((_resolve, reject) => {
            rejectFirst = reject
          })
      )
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveSecond = resolve
          })
      )
    const view = render(<NewsCard {...baseProps} />)

    fireEvent.click(screen.getByRole("button", { name: "open edit" }))
    await waitFor(() => expect(mocks.fetchNewsItem).toHaveBeenCalledTimes(1))
    const firstOptions = mocks.fetchNewsItem.mock.calls[0]?.[1] as { signal: AbortSignal }

    mocks.language = "ru"
    view.rerender(<NewsCard {...baseProps} onChange={() => undefined} />)
    expect(firstOptions.signal.aborted).toBe(true)
    mocks.language = "en"
    view.rerender(<NewsCard {...baseProps} onChange={() => undefined} />)
    fireEvent.click(screen.getByRole("button", { name: "open edit" }))
    await waitFor(() => expect(mocks.fetchNewsItem).toHaveBeenCalledTimes(2))

    await act(async () => {
      rejectFirst(new Error("superseded source request"))
      await Promise.resolve()
    })
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
    expect(mocks.viewRender.mock.calls.at(-1)?.[0].loading).toBe(true)

    await act(async () => {
      resolveSecond({
        status: 200,
        data: {
          id: "news-1",
          title: "Источник",
          content: "Исходный текст",
          title_en: null,
          content_en: null,
          image_url: null,
        },
      })
    })
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument())
    expect(mocks.viewRender.mock.calls.at(-1)?.[0].editData).toEqual({
      title: "Источник",
      content: "Исходный текст",
      title_en: "",
      content_en: "",
      image_url: "",
    })
  })

  it("does not open the English editor when the Russian source request fails", async () => {
    mocks.user = { role: "admin" }
    mocks.fetchNewsItem.mockRejectedValueOnce(new Error("source unavailable"))
    render(<NewsCard {...baseProps} />)

    fireEvent.click(screen.getByRole("button", { name: "open edit" }))
    expect(await screen.findByRole("status")).toHaveTextContent("common:errors.generic")
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("does not open the English editor for a not-modified Russian source response", async () => {
    mocks.user = { role: "admin" }
    mocks.fetchNewsItem.mockResolvedValueOnce({ status: 304, data: undefined })
    render(<NewsCard {...baseProps} />)

    fireEvent.click(screen.getByRole("button", { name: "open edit" }))
    expect(await screen.findByRole("status")).toHaveTextContent("common:errors.generic")
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("aborts the source request on unmount without publishing a late result", async () => {
    mocks.user = { role: "admin" }
    let resolveSource!: (value: { status: number; data: Record<string, string> }) => void
    mocks.fetchNewsItem.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveSource = resolve
      })
    )
    const { unmount } = render(<NewsCard {...baseProps} />)

    fireEvent.click(screen.getByRole("button", { name: "open edit" }))
    const options = mocks.fetchNewsItem.mock.calls[0]?.[1] as { signal: AbortSignal }
    unmount()
    expect(options.signal.aborted).toBe(true)

    await act(async () => {
      resolveSource({
        status: 200,
        data: {
          id: "news-1",
          title: "Late Russian title",
          content: "Late Russian body",
          title_en: "Late English title",
          content_en: "Late English body",
          image_url: "/late.png",
        },
      })
    })
    expect(screen.queryByTestId("news-card-view")).not.toBeInTheDocument()
  })

  it("surfaces delete errors and lets the caller close them", async () => {
    mocks.user = { role: "admin" }
    mocks.deleteNews.mockRejectedValue(new Error("delete failed"))
    render(<NewsCard {...baseProps} />)

    fireEvent.click(screen.getByRole("button", { name: "open delete" }))
    fireEvent.click(screen.getByRole("button", { name: "confirm delete" }))
    expect(await screen.findByRole("status")).toHaveTextContent("common:errors.generic")
    fireEvent.click(screen.getByRole("button", { name: "close error" }))
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
  })

  it("does not publish a late sanitizer result after unmount", async () => {
    let resolveSanitizer!: (value: string) => void
    mocks.sanitizeNewsText.mockReturnValueOnce(
      new Promise<string>((resolve) => {
        resolveSanitizer = resolve
      })
    )
    const { unmount } = render(<NewsCard {...baseProps} />)

    unmount()
    resolveSanitizer("late preview")
    await Promise.resolve()

    expect(screen.queryByTestId("news-card-view")).not.toBeInTheDocument()
  })
})

describe("NewsCard — derived state follows props", () => {
  const lastViewProps = () =>
    mocks.viewRender.mock.calls.at(-1)?.[0] as {
      loading: boolean
      category: string
      readingTime: number
      previewText: string
      title: string
      editData: Record<string, string>
    }

  it("seeds the interaction query with the card's initial counters", async () => {
    render(<NewsCard {...baseProps} />)
    await waitFor(() => expect(screen.getByTestId("card-preview")).toHaveTextContent("sanitized:"))

    expect(mocks.interactionArgs.at(-1)).toEqual([
      "news-1",
      {
        initialData: { likes_count: 4, comments_count: 2, is_liked: false },
        loadComments: false,
      },
    ])
  })

  it("starts idle, without a preview until sanitizing finishes", async () => {
    let resolveSanitizer!: (value: string) => void
    mocks.sanitizeNewsText.mockReturnValueOnce(
      new Promise<string>((resolve) => {
        resolveSanitizer = resolve
      })
    )
    render(<NewsCard {...baseProps} />)

    expect(lastViewProps().loading).toBe(false)
    expect(screen.getByTestId("card-preview")).toHaveTextContent(/^$/)

    resolveSanitizer("clean preview")
    expect(await screen.findByText("clean preview")).toBeInTheDocument()
  })

  it("recomputes title, preview, category, reading time and edit data on prop changes", async () => {
    mocks.user = { role: "admin" }
    mocks.language = "ru"
    const { rerender } = render(<NewsCard {...baseProps} />)
    await waitFor(() =>
      expect(screen.getByTestId("card-preview")).toHaveTextContent(
        "sanitized:ru:The campus library is open."
      )
    )

    rerender(
      <NewsCard
        {...baseProps}
        title="Exam week"
        title_en="Exam week EN"
        content="Library hours extended."
        content_en="Library hours extended EN."
        image_url="/exam.png"
      />
    )

    await waitFor(() =>
      expect(screen.getByTestId("card-preview")).toHaveTextContent(
        "sanitized:ru:Library hours extended."
      )
    )
    const props = lastViewProps()
    expect(props.title).toBe("ru:Exam week")
    expect(props.category).toBe("category:Exam week EN|Library hours extended EN.")
    expect(props.readingTime).toBe("ru:Library hours extended.".length)

    const user = userEvent.setup()
    await user.click(screen.getByRole("button", { name: "open edit" }))
    await screen.findByRole("dialog")
    const editProps = lastViewProps()
    expect(editProps.editData).toEqual({
      title: "Exam week",
      content: "Library hours extended.",
      title_en: "Exam week EN",
      content_en: "Library hours extended EN.",
      image_url: "/exam.png",
    })
  })

  it("keeps the newest preview when an older sanitizer run settles late", async () => {
    let resolveFirst!: (value: string) => void
    mocks.sanitizeNewsText.mockReturnValueOnce(
      new Promise<string>((resolve) => {
        resolveFirst = resolve
      })
    )
    const { rerender } = render(<NewsCard {...baseProps} />)
    rerender(<NewsCard {...baseProps} content="Second body" />)
    await waitFor(() =>
      expect(screen.getByTestId("card-preview")).toHaveTextContent("sanitized:en:Second body")
    )

    await act(async () => {
      resolveFirst("stale first preview")
      await Promise.resolve()
    })

    expect(screen.getByTestId("card-preview")).toHaveTextContent("sanitized:en:Second body")
  })

  it("hides admin-only controls from non-admin readers", async () => {
    mocks.user = { role: "student" }
    render(<NewsCard {...baseProps} />)
    await waitFor(() => expect(screen.getByTestId("card-preview")).toHaveTextContent("sanitized:"))
    expect(screen.queryByRole("button", { name: "open delete" })).not.toBeInTheDocument()
  })

  it("closes the edit dialog when the view asks to", async () => {
    mocks.user = { role: "admin" }
    const user = userEvent.setup()
    render(<NewsCard {...baseProps} />)
    await waitFor(() => expect(screen.getByTestId("card-preview")).toHaveTextContent("sanitized:"))
    await user.click(screen.getByRole("button", { name: "open edit" }))
    expect(await screen.findByRole("dialog")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "close edit" }))
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
  })

  it("deletes successfully without an onChange listener and shows no error", async () => {
    mocks.user = { role: "admin" }
    const user = userEvent.setup()
    render(<NewsCard {...baseProps} />)
    await waitFor(() => expect(screen.getByTestId("card-preview")).toHaveTextContent("sanitized:"))

    await user.click(screen.getByRole("button", { name: "open delete" }))
    await user.click(screen.getByRole("button", { name: "confirm delete" }))
    await act(async () => {
      await mocks.deleteNews.mock.results[0]?.value
    })

    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument())
    expect(mocks.deleteNews).toHaveBeenCalledWith("/news/news-1")
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
  })

  it("deletes and notifies using the latest id and onChange", async () => {
    mocks.user = { role: "admin" }
    const user = userEvent.setup()
    const staleOnChange = vi.fn()
    const onChange = vi.fn()
    const { rerender } = render(<NewsCard {...baseProps} onChange={staleOnChange} />)
    rerender(<NewsCard {...baseProps} id="news-9" onChange={onChange} />)
    await waitFor(() => expect(screen.getByTestId("card-preview")).toHaveTextContent("sanitized:"))

    await user.click(screen.getByRole("button", { name: "open edit" }))
    await screen.findByRole("dialog")
    await user.click(screen.getByRole("button", { name: "edit success" }))
    await user.click(screen.getByRole("button", { name: "open delete" }))
    await user.click(screen.getByRole("button", { name: "confirm delete" }))
    await act(async () => {
      await mocks.deleteNews.mock.results[0]?.value
    })

    await waitFor(() => expect(onChange).toHaveBeenCalledTimes(2))
    expect(mocks.deleteNews).toHaveBeenCalledWith("/news/news-9")
    expect(staleOnChange).not.toHaveBeenCalled()
  })
})
