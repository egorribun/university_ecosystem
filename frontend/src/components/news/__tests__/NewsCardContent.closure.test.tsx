import { createElement } from "react"
import { act, fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const translationState = vi.hoisted(() => ({ namespaces: [] as unknown[] }))
const linkState = vi.hoisted(() => ({ params: undefined as unknown }))

vi.mock("react-i18next", () => ({
  useTranslation: (namespaces?: unknown) => {
    translationState.namespaces.push(namespaces)
    return { t: (key: string) => key }
  },
}))

vi.mock("@tanstack/react-router", () => ({
  Link: ({
    children,
    to,
    params,
    ...props
  }: { children?: unknown; to?: string; params?: unknown } & Record<string, unknown>) => {
    linkState.params = params
    return createElement("a", { href: to ?? "#", ...props }, children as never)
  },
}))

import NewsCardContent from "@/components/news/NewsCardContent"

const baseProps = {
  id: "news-1",
  title: "Research update",
  preview: "A short preview",
  isLiked: false,
  likesCount: 4,
  commentsCount: 2,
  hoveringDisabled: false,
  onToggleLike: vi.fn(),
}

beforeEach(() => {
  translationState.namespaces.length = 0
  linkState.params = undefined
})

describe("NewsCardContent closure", () => {
  it("handles like celebration, reading time, and bookmark toggles", () => {
    const onToggleLike = vi.fn()
    const onToggleBookmark = vi.fn()
    render(
      <NewsCardContent
        {...baseProps}
        onToggleLike={onToggleLike}
        onToggleBookmark={onToggleBookmark}
        readingTime={5}
      />
    )

    expect(screen.getByRole("link", { name: "Research update" })).toHaveAttribute(
      "href",
      "/news/$id"
    )
    expect(linkState.params).toEqual({ id: "news-1" })
    expect(translationState.namespaces.at(-1)).toEqual(["common"])
    expect(screen.getByText("5 common:time.minuteShort")).toBeInTheDocument()
    expect(screen.getByText("common:cta.learnMore")).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "common:aria.like" }).querySelector("svg")
    ).toHaveAttribute("fill", "none")
    fireEvent.click(screen.getByRole("button", { name: "common:aria.like" }))
    fireEvent.click(screen.getByRole("button", { name: "common:aria.addBookmark" }))
    expect(onToggleLike).toHaveBeenCalledTimes(1)
    expect(onToggleBookmark).toHaveBeenCalledTimes(1)
  })

  it("does not start a celebration when an already-liked article is toggled", () => {
    const onToggleLike = vi.fn()
    render(<NewsCardContent {...baseProps} isLiked onToggleLike={onToggleLike} />)

    const likeButton = screen.getByRole("button", { name: "common:aria.unlike" })
    expect(likeButton.querySelector("svg")).toHaveAttribute("fill", "currentColor")
    fireEvent.click(likeButton)

    expect(onToggleLike).toHaveBeenCalledOnce()
    expect(likeButton.querySelector(".news-heart-celebrate")).not.toBeInTheDocument()
  })

  it("renders a zero-minute reading time and omits undefined reading time", () => {
    const { rerender } = render(<NewsCardContent {...baseProps} readingTime={0} />)

    expect(screen.getByText("0 common:time.minuteShort")).toBeInTheDocument()
    rerender(<NewsCardContent {...baseProps} />)
    expect(screen.queryByText("0 common:time.minuteShort")).not.toBeInTheDocument()
  })

  it("does not render bookmark controls when no bookmark callback is supplied", () => {
    render(<NewsCardContent {...baseProps} onToggleBookmark={undefined} />)

    expect(
      screen.queryByRole("button", { name: "common:aria.addBookmark" })
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: "common:aria.removeBookmark" })
    ).not.toBeInTheDocument()
  })

  it("stops like and bookmark clicks from bubbling to the card container", () => {
    const onCardClick = vi.fn()
    const onToggleLike = vi.fn()
    const onToggleBookmark = vi.fn()
    const host = document.createElement("div")
    const outer = document.createElement("div")
    host.append(outer)
    document.body.append(host)
    const { unmount } = render(
      <NewsCardContent
        {...baseProps}
        onToggleLike={onToggleLike}
        onToggleBookmark={onToggleBookmark}
      />,
      { container: outer }
    )
    host.addEventListener("click", onCardClick)

    fireEvent.click(screen.getByRole("button", { name: "common:aria.like" }))
    fireEvent.click(screen.getByRole("button", { name: "common:aria.addBookmark" }))

    expect(onToggleLike).toHaveBeenCalledOnce()
    expect(onToggleBookmark).toHaveBeenCalledOnce()
    expect(onCardClick).not.toHaveBeenCalled()
    unmount()
    host.remove()
  })

  it("removes the like celebration class after its animation window", () => {
    vi.useFakeTimers()

    try {
      render(<NewsCardContent {...baseProps} />)
      const likeButton = screen.getByRole("button", { name: "common:aria.like" })

      fireEvent.click(likeButton)
      expect(likeButton.querySelector(".news-heart-celebrate")).toBeInTheDocument()

      act(() => {
        vi.advanceTimersByTime(400)
      })
      expect(likeButton.querySelector(".news-heart-celebrate")).not.toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it("clears a pending like celebration timer on unmount", () => {
    vi.useFakeTimers()
    const clearTimeoutSpy = vi.spyOn(globalThis, "clearTimeout")

    try {
      const { unmount } = render(<NewsCardContent {...baseProps} />)
      fireEvent.click(screen.getByRole("button", { name: "common:aria.like" }))
      clearTimeoutSpy.mockClear()

      unmount()

      expect(clearTimeoutSpy).toHaveBeenCalledTimes(1)
    } finally {
      vi.useRealTimers()
      clearTimeoutSpy.mockRestore()
    }
  })

  it("replaces an existing like celebration timer on a repeated click", () => {
    vi.useFakeTimers()
    const clearTimeoutSpy = vi.spyOn(globalThis, "clearTimeout")

    try {
      render(<NewsCardContent {...baseProps} />)
      const likeButton = screen.getByRole("button", { name: "common:aria.like" })

      fireEvent.click(likeButton)
      clearTimeoutSpy.mockClear()
      fireEvent.click(likeButton)

      expect(clearTimeoutSpy).toHaveBeenCalledTimes(1)
    } finally {
      vi.useRealTimers()
      clearTimeoutSpy.mockRestore()
    }
  })

  it("renders liked and bookmarked state without optional controls", () => {
    const onToggleLike = vi.fn()
    const onToggleBookmark = vi.fn()
    render(
      <NewsCardContent
        {...baseProps}
        isLiked
        isBookmarked
        onToggleLike={onToggleLike}
        onToggleBookmark={onToggleBookmark}
        hoveringDisabled
        readingTime={null}
      />
    )

    const link = screen.getByRole("link", { name: "Research update" })
    expect(link).toHaveClass("pointer-events-none")
    expect(screen.getByRole("button", { name: "common:aria.unlike" })).toBeInTheDocument()
    const bookmark = screen.getByRole("button", { name: "common:aria.removeBookmark" })
    fireEvent.click(bookmark)
    fireEvent.click(screen.getByRole("button", { name: "common:aria.unlike" }))
    expect(onToggleLike).toHaveBeenCalledTimes(1)
    expect(onToggleBookmark).toHaveBeenCalledTimes(1)
  })
})
