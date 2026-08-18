import { createElement } from "react"
import { act, fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

vi.mock("@tanstack/react-router", () => ({
  Link: ({
    children,
    to,
    ...props
  }: { children?: unknown; to?: string } & Record<string, unknown>) =>
    createElement("a", { href: to ?? "#", ...props }, children as never),
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
    expect(screen.getByText("5 common:time.minuteShort")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "common:aria.like" }))
    fireEvent.click(screen.getByRole("button", { name: "common:aria.addBookmark" }))
    expect(onToggleLike).toHaveBeenCalledTimes(1)
    expect(onToggleBookmark).toHaveBeenCalledTimes(1)
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
