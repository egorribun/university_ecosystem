import { act, fireEvent, render, screen } from "@testing-library/react"
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

const queryState = vi.hoisted(() => ({
  data: undefined as unknown,
  isLoading: false,
  options: undefined as { queryFn: () => Promise<unknown> } | undefined,
}))
vi.mock("@tanstack/react-query", () => ({
  useQuery: (options: { queryFn: () => Promise<unknown> }) => {
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

describe("SearchDialog", () => {
  beforeEach(() => {
    queryState.data = undefined
    queryState.isLoading = false
    queryState.options = undefined
    apiGetMock.mockReset()
    navigateMock.mockClear()
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
  })

  it("renders nothing until the Cmd/Ctrl+K shortcut opens it", () => {
    const { container } = render(<SearchDialog />)
    expect(container.firstChild).toBeNull()

    openDialog()
    expect(screen.getByRole("dialog", { name: "common:search.title" })).toBeInTheDocument()
    expect(screen.getByPlaceholderText("common:search.placeholder")).toBeInTheDocument()
  })

  it("shows the empty-state hint when no query and no recent searches", () => {
    render(<SearchDialog />)
    openDialog()
    expect(screen.getByText("common:search.hint")).toBeInTheDocument()
  })

  it("shows recent searches from localStorage when present and no query", () => {
    localStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(["calculus", "lab report"]))
    render(<SearchDialog />)
    openDialog()
    expect(screen.getByText("common:search.recent")).toBeInTheDocument()
    expect(screen.getByText("calculus")).toBeInTheDocument()
    expect(screen.getByText("lab report")).toBeInTheDocument()
  })

  it("loads a recent search and closes when the backdrop is clicked", async () => {
    localStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(["calculus"]))
    const user = userEvent.setup()
    render(<SearchDialog />)
    openDialog()

    await user.click(screen.getByRole("button", { name: "calculus" }))
    expect(screen.getByPlaceholderText<HTMLInputElement>("common:search.placeholder")).toHaveValue(
      "calculus"
    )

    await user.click(screen.getByRole("presentation"))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("renders the loading spinner branch while a 2+ char query is in flight", async () => {
    queryState.isLoading = true
    const user = userEvent.setup()
    render(<SearchDialog />)
    openDialog()
    const input = screen.getByPlaceholderText("common:search.placeholder")
    await user.type(input, "ph")
    // Spinner has no text/role; assert the no-results / hint copy is NOT shown while loading
    expect(screen.queryByText("common:search.noResults")).not.toBeInTheDocument()
    expect(screen.queryByText("common:search.hint")).not.toBeInTheDocument()
  })

  it("renders grouped results and navigates on click", async () => {
    queryState.data = {
      query: "phys",
      results: {
        news: [
          {
            id: "n1",
            type: "news",
            title: "Physics News",
            summary: "About physics",
            score: 0.9,
            url: "/news/n1",
          },
        ],
        events: [
          {
            id: "e1",
            type: "events",
            title: "Physics Event",
            summary: "",
            score: 0.7,
            url: "/events/e1",
          },
        ],
      },
    }
    const user = userEvent.setup()
    render(<SearchDialog />)
    openDialog()
    const input = screen.getByPlaceholderText("common:search.placeholder")
    await user.type(input, "phys")

    const newsResult = screen.getByText("Physics News")
    expect(newsResult).toBeInTheDocument()
    expect(screen.getByText("Physics Event")).toBeInTheDocument()
    expect(screen.getByText("About physics")).toBeInTheDocument()

    await user.click(newsResult)
    expect(navigateMock).toHaveBeenCalledWith({ to: "/news/n1" })
  })

  it("shows the no-results state when the query returns nothing", async () => {
    queryState.data = { query: "zzz", results: {} }
    const user = userEvent.setup()
    render(<SearchDialog />)
    openDialog()
    const input = screen.getByPlaceholderText("common:search.placeholder")
    await user.type(input, "zzz")
    expect(screen.getByText("common:search.noResults")).toBeInTheDocument()
  })

  it("builds the API request through the query function", async () => {
    const user = userEvent.setup()
    const response = { query: "phys", results: {} }
    apiGetMock.mockResolvedValue({ data: response })
    render(<SearchDialog />)
    openDialog()
    await user.type(screen.getByPlaceholderText("common:search.placeholder"), "phys")

    const queryFn = queryState.options?.queryFn
    expect(queryFn).toBeDefined()
    await expect(queryFn?.()).resolves.toEqual(response)
    expect(apiGetMock).toHaveBeenCalledWith("/search", {
      params: { q: "phys", type: "all", limit: 8 },
    })
  })

  it("supports keyboard result navigation, active-item scrolling, and Enter selection", async () => {
    localStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(["phys", "calculus"]))
    queryState.data = {
      query: "phys",
      results: {
        news: [
          {
            id: "n1",
            type: "news",
            title: "Physics News",
            summary: "About physics",
            score: 0.9,
            url: "/news/n1",
          },
          {
            id: "n2",
            type: "news",
            title: "Physics Lab",
            summary: "",
            score: 0.8,
            url: "/news/n2",
          },
        ],
      },
    }
    const user = userEvent.setup()
    const scrollIntoView = vi
      .spyOn(Element.prototype, "scrollIntoView")
      .mockImplementation(() => undefined)

    render(<SearchDialog />)
    openDialog()
    const input = screen.getByPlaceholderText<HTMLInputElement>("common:search.placeholder")
    await user.type(input, "phys")
    const items = document.querySelectorAll<HTMLButtonElement>("[data-search-item]")

    fireEvent.keyDown(input, { key: "ArrowDown" })
    expect(items[0]).toHaveClass("bg-brand/(--opacity-subtle)")
    expect(scrollIntoView).toHaveBeenCalledWith({ block: "nearest" })

    fireEvent.keyDown(input, { key: "ArrowDown" })
    expect(items[1]).toHaveClass("bg-brand/(--opacity-subtle)")
    fireEvent.keyDown(input, { key: "ArrowUp" })
    expect(items[0]).toHaveClass("bg-brand/(--opacity-subtle)")
    fireEvent.keyDown(input, { key: "Enter" })

    expect(navigateMock).toHaveBeenCalledWith({ to: "/news/n1" })
    expect(JSON.parse(localStorage.getItem(RECENT_SEARCHES_KEY) ?? "null")).toEqual([
      "phys",
      "calculus",
    ])
    scrollIntoView.mockRestore()
  })

  it("ignores malformed recent-search storage and closes on Escape", () => {
    localStorage.setItem(RECENT_SEARCHES_KEY, "{not-json")
    render(<SearchDialog />)
    openDialog()
    expect(screen.getByText("common:search.hint")).toBeInTheDocument()

    fireEvent.keyDown(document, { key: "Escape" })
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("keeps navigation working when recent-search persistence is unavailable", async () => {
    queryState.data = {
      query: "phys",
      results: {
        news: [
          {
            id: "n1",
            type: "news",
            title: "Physics News",
            summary: "",
            score: 1,
            url: "/news/n1",
          },
        ],
      },
    }
    const user = userEvent.setup()
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota")
    })

    render(<SearchDialog />)
    openDialog()
    await user.type(screen.getByPlaceholderText("common:search.placeholder"), "phys")
    await user.click(screen.getByText("Physics News"))

    expect(navigateMock).toHaveBeenCalledWith({ to: "/news/n1" })
    setItem.mockRestore()
  })

  it("uses the Mac shortcut label and a safe fallback icon for unknown result types", async () => {
    const platform = vi.spyOn(window.navigator, "platform", "get").mockReturnValue("MacIntel")
    queryState.data = {
      query: "campus",
      results: {
        events: [
          {
            id: "unknown-1",
            type: "unknown",
            title: "Campus result",
            summary: "",
            score: 1,
            url: "/search/unknown-1",
          },
        ],
      },
    }
    const user = userEvent.setup()

    render(<SearchDialog />)
    openDialog()
    await user.type(screen.getByPlaceholderText("common:search.placeholder"), "campus")

    expect(screen.getByText("Campus result")).toBeInTheDocument()
    expect(screen.getByText("⌘+K")).toBeInTheDocument()
    platform.mockRestore()
  })

  it("clears the query via the clear button and exposes nav/select footer hints", async () => {
    const user = userEvent.setup()
    render(<SearchDialog />)
    openDialog()
    const input = screen.getByPlaceholderText<HTMLInputElement>("common:search.placeholder")
    await user.type(input, "ab")
    expect(input.value).toBe("ab")

    await user.click(screen.getByRole("button", { name: "common:search.clear" }))
    expect(input.value).toBe("")

    expect(screen.getByText("common:search.navigate")).toBeInTheDocument()
    expect(screen.getByText("common:search.select")).toBeInTheDocument()
  })
})
