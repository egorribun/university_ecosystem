import { act } from "react"
import { hydrateRoot, type Root } from "react-dom/client"
import { renderToString } from "react-dom/server"
import { afterEach, expect, it, vi } from "vitest"

type BookmarkHook = () => {
  isBookmarked: (id: string) => boolean
  bookmarkCount: number
}

let useServerBookmarks!: BookmarkHook
let useBrowserBookmarks!: BookmarkHook

function BookmarkMarkup({ isBookmarked, bookmarkCount }: ReturnType<BookmarkHook>) {
  const bookmarked = isBookmarked("story-returning")

  return (
    <section>
      <output aria-label="Bookmark count">{bookmarkCount}</output>
      <button type="button" aria-label={bookmarked ? "Remove bookmark" : "Add bookmark"}>
        {bookmarked ? "Bookmarked" : "Not bookmarked"}
      </button>
    </section>
  )
}

function ServerBookmarkProbe() {
  return <BookmarkMarkup {...useServerBookmarks()} />
}

function BrowserBookmarkProbe() {
  return <BookmarkMarkup {...useBrowserBookmarks()} />
}

const STORAGE_KEY = "news:bookmarks"
const originalStorage = Object.getOwnPropertyDescriptor(globalThis, "localStorage")

let root: Root | undefined
let container: HTMLDivElement | undefined

afterEach(async () => {
  if (root) {
    await act(async () => root?.unmount())
    root = undefined
  }
  container?.remove()
  container = undefined
  if (originalStorage) {
    Object.defineProperty(globalThis, "localStorage", originalStorage)
    globalThis.localStorage?.removeItem(STORAGE_KEY)
  } else {
    Reflect.deleteProperty(globalThis, "localStorage")
  }
  vi.resetModules()
})

it("hydrates the empty server snapshot before restoring a returning user's bookmarks", async () => {
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    get() {
      throw new Error("Server rendering has no localStorage")
    },
  })
  vi.resetModules()
  const { useBookmarks: serverUseBookmarks } = await import("../useBookmarks")
  useServerBookmarks = serverUseBookmarks
  const serverMarkup = renderToString(<ServerBookmarkProbe />)

  expect(serverMarkup).toContain('<output aria-label="Bookmark count">0</output>')
  expect(serverMarkup).toContain('aria-label="Add bookmark"')

  if (originalStorage) Object.defineProperty(globalThis, "localStorage", originalStorage)
  globalThis.localStorage?.setItem(STORAGE_KEY, JSON.stringify(["story-returning"]))
  vi.resetModules()
  const { useBookmarks: browserUseBookmarks } = await import("../useBookmarks")
  useBrowserBookmarks = browserUseBookmarks

  container = document.createElement("div")
  container.innerHTML = serverMarkup
  document.body.append(container)
  const recoverableErrors: unknown[] = []

  await act(async () => {
    root = hydrateRoot(container as HTMLDivElement, <BrowserBookmarkProbe />, {
      onRecoverableError: (error) => recoverableErrors.push(error),
    })
  })

  expect(recoverableErrors).toEqual([])
  expect(container.querySelector('[aria-label="Bookmark count"]')?.textContent).toBe("1")
  expect(container.querySelector("button")?.getAttribute("aria-label")).toBe("Remove bookmark")
  expect(globalThis.localStorage?.getItem(STORAGE_KEY)).toBe(JSON.stringify(["story-returning"]))
})
