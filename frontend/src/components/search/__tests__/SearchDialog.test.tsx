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

vi.mock("@/api/client", () => ({ default: { get: vi.fn() } }))

const queryState = vi.hoisted(() => ({
  data: undefined as unknown,
  isLoading: false,
}))
vi.mock("@tanstack/react-query", () => ({
  useQuery: () => ({ data: queryState.data, isLoading: queryState.isLoading }),
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
