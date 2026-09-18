import { act, createEvent, fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

const navigateMock = vi.fn()
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => navigateMock,
}))

vi.mock("@/hooks/useDebounced", () => ({
  useDebounced: (value: unknown) => value,
}))

const apiGetMock = vi.hoisted(() => vi.fn())
vi.mock("@/api/client", () => ({ default: { get: apiGetMock } }))

type QueryOptions = {
  queryKey: unknown[]
  queryFn: () => Promise<unknown>
  enabled: boolean
  staleTime: number
}

const queryState = vi.hoisted(() => ({
  data: undefined as unknown,
  isLoading: false,
  options: undefined as QueryOptions | undefined,
}))
vi.mock("@tanstack/react-query", () => ({
  useQuery: (options: QueryOptions) => {
    queryState.options = options
    return { data: queryState.data, isLoading: queryState.isLoading }
  },
}))

import { SearchDialog } from "@/components/search/SearchDialog"

const RECENT_SEARCHES_KEY = "ue:recent-searches"

function openDialog() {
  act(() => {
    fireEvent.keyDown(document, { key: "k", ctrlKey: true })
  })
}

function makeResult(
  overrides: Partial<{
    id: string
    type: "news" | "events"
    title: string
    summary: string
    score: number
    url: string
  }> = {}
) {
  return {
    id: "result",
    type: "news" as const,
    title: "Result",
    summary: "Summary",
    score: 1,
    url: "/news/result",
    ...overrides,
  }
}

describe("SearchDialog mutation contracts", () => {
  beforeEach(() => {
    queryState.data = undefined
    queryState.isLoading = false
    queryState.options = undefined
    apiGetMock.mockReset()
    navigateMock.mockReset()
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it("requires the exact Ctrl/Cmd+K shortcut and prevents its default action", () => {
    const { unmount } = render(<SearchDialog />)
    const preventDefault = vi.fn()

    fireEvent.keyDown(document, { key: "x", ctrlKey: true })
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()

    const shortcut = createEvent.keyDown(document, { key: "k", ctrlKey: true })
    shortcut.preventDefault = preventDefault
    fireEvent(document, shortcut)
    expect(preventDefault).toHaveBeenCalledTimes(1)
    expect(screen.getByRole("dialog", { name: "common:search.title" })).toBeInTheDocument()

    fireEvent.keyDown(document, { key: "k", metaKey: true, preventDefault })
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    unmount()
  })

  it("removes the global keyboard listener on unmount", () => {
    const { unmount } = render(<SearchDialog />)
    unmount()
    fireEvent.keyDown(document, { key: "k", ctrlKey: true })
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("closes only an open dialog for Escape and resets its query and selection", async () => {
    const user = userEvent.setup()
    render(<SearchDialog />)
    openDialog()
    const input = screen.getByRole("textbox", { name: "common:search.inputLabel" })
    await user.type(input, "ab")
    fireEvent.keyDown(document, { key: "Escape" })
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()

    openDialog()
    expect(screen.getByRole("textbox", { name: "common:search.inputLabel" })).toHaveValue("")
  })

  it("focuses the input on open through requestAnimationFrame", () => {
    const callbacks: FrameRequestCallback[] = []
    const raf = vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      callbacks.push(callback)
      return callbacks.length
    })
    render(<SearchDialog />)
    openDialog()
    expect(raf).toHaveBeenCalledTimes(1)
    expect(document.activeElement).not.toBe(screen.getByRole("textbox"))
    act(() => callbacks[0]?.(0))
    expect(document.activeElement).toBe(screen.getByRole("textbox"))
  })

  it("bounds recent searches to five entries and deduplicates the selected query", async () => {
    localStorage.setItem(
      RECENT_SEARCHES_KEY,
      JSON.stringify(["old", "phys", "one", "two", "three", "four", "five"])
    )
    queryState.data = { results: { news: [makeResult({ id: "n1", title: "Physics" })] } }
    const user = userEvent.setup()
    render(<SearchDialog />)
    openDialog()

    expect(screen.getByText("old")).toBeInTheDocument()
    expect(screen.queryByText("five")).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "phys" }))
    await user.click(screen.getByText("Physics"))

    expect(JSON.parse(localStorage.getItem(RECENT_SEARCHES_KEY) ?? "null")).toEqual([
      "phys",
      "old",
      "one",
      "two",
      "three",
    ])
  })

  it("fails closed for null, object, and malformed recent-search storage", () => {
    for (const value of ["null", "{}", "not-json"]) {
      localStorage.setItem(RECENT_SEARCHES_KEY, value)
      const { unmount } = render(<SearchDialog />)
      openDialog()
      expect(screen.getByText("common:search.hint")).toBeInTheDocument()
      unmount()
      document.body.innerHTML = ""
    }
  })

  it("publishes the query key, enabled threshold, stale time, and request contract", async () => {
    const user = userEvent.setup()
    render(<SearchDialog />)
    expect(queryState.options).toMatchObject({
      queryKey: ["search", ""],
      enabled: false,
      staleTime: 30_000,
    })
    openDialog()
    await user.type(screen.getByRole("textbox"), "a")
    expect(queryState.options).toMatchObject({ queryKey: ["search", "a"], enabled: false })
    await user.type(screen.getByRole("textbox"), "b")
    expect(queryState.options).toMatchObject({ queryKey: ["search", "ab"], enabled: true })

    const response = { query: "ab", results: {} }
    apiGetMock.mockResolvedValue({ data: response })
    await expect(queryState.options?.queryFn()).resolves.toEqual(response)
    expect(apiGetMock).toHaveBeenCalledWith("/search", {
      params: { q: "ab", type: "all", limit: 8 },
    })
  })

  it("sorts mixed result types by score and renders summary/icon fallbacks", async () => {
    queryState.data = {
      results: {
        news: [makeResult({ id: "low", title: "Low", score: 0.2, summary: "Details" })],
        events: [
          makeResult({
            id: "high",
            type: "events",
            title: "High",
            score: 0.9,
            summary: "",
          }),
          makeResult({ id: "mid", type: "events", title: "Mid", score: 0.5, summary: "" }),
        ],
      },
    }
    const user = userEvent.setup()
    render(<SearchDialog />)
    openDialog()
    await user.type(screen.getByRole("textbox"), "abc")

    const items = [...document.querySelectorAll<HTMLButtonElement>("[data-search-item]")]
    expect(items.map((item) => item.textContent)).toEqual(["High", "Mid", "LowDetails"])
    expect(screen.getByText("Details")).toBeInTheDocument()
    expect(screen.queryAllByRole("img")).toHaveLength(0)
    expect(items[0]?.querySelector("svg")).toHaveAttribute("aria-hidden", "true")
    expect(items[2]?.querySelector("svg")).toHaveAttribute("aria-hidden", "true")
  })

  it("keeps arrow navigation within bounds and selects only an active result", async () => {
    queryState.data = {
      results: {
        news: [
          makeResult({ id: "one", title: "One" }),
          makeResult({ id: "two", title: "Two", score: 0.5 }),
        ],
      },
    }
    const user = userEvent.setup()
    const scrollIntoView = vi
      .spyOn(Element.prototype, "scrollIntoView")
      .mockImplementation(() => {})
    render(<SearchDialog />)
    openDialog()
    const input = screen.getByRole("textbox")
    await user.type(input, "ab")

    fireEvent.keyDown(input, { key: "ArrowUp" })
    expect(
      document.querySelector("[data-search-item].bg-brand\\/\\(--opacity-subtle\\)")
    ).not.toBeInTheDocument()
    fireEvent.keyDown(input, { key: "ArrowDown" })
    fireEvent.keyDown(input, { key: "ArrowDown" })
    fireEvent.keyDown(input, { key: "ArrowDown" })
    expect(screen.getByText("Two").closest("button")).toHaveClass("bg-brand/(--opacity-subtle)")
    expect(scrollIntoView).toHaveBeenCalledWith({ block: "nearest" })

    fireEvent.keyDown(input, { key: "Enter" })
    expect(navigateMock).toHaveBeenCalledWith({ to: "/news/result" })
  })

  it("exposes the stable dialog, field, clear affordance, result, and footer semantics", async () => {
    const user = userEvent.setup()
    render(<SearchDialog />)
    openDialog()
    const dialog = screen.getByRole("dialog", { name: "common:search.title" })
    expect(dialog).toHaveAttribute("aria-modal", "true")
    expect(dialog).toHaveClass("glass-layer-floating", "w-full", "max-w-[36rem]")
    expect(screen.getByRole("presentation")).toHaveClass("fixed", "inset-0", "z-modal")
    expect(screen.getByRole("textbox")).toHaveAttribute("type", "text")
    expect(screen.getByText("common:search.navigate")).toBeInTheDocument()
    expect(screen.getByText("common:search.select")).toBeInTheDocument()

    await user.type(screen.getByRole("textbox"), "ab")
    const clear = screen.getByRole("button", { name: "common:search.clear" })
    expect(clear).toHaveClass("min-h-[44px]", "min-w-[44px]")
    await user.click(clear)
    expect(screen.getByRole("textbox")).toHaveValue("")
  })
})
