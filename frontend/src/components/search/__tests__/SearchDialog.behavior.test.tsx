import {
  act,
  cleanup,
  createEvent,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router"
import { createInstance } from "i18next"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { SearchDialog } from "@/components/search/SearchDialog"
import enCommon from "@/i18n/locales/en/common.json"
import ruCommon from "@/i18n/locales/ru/common.json"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)

const apiGet = vi.hoisted(() => vi.fn())
vi.mock("@/api/client", () => ({ default: { get: apiGet } }))

const RECENT_SEARCHES_KEY = "ue:recent-searches"
const clients: QueryClient[] = []

const response = {
  query: "physics",
  results: {
    news: [
      {
        id: "101",
        type: "news",
        title: "Physics news",
        summary: "New campus laboratory",
        score: 0.5,
        url: "/news/101",
      },
    ],
    events: [
      {
        id: "202",
        type: "events",
        title: "Physics seminar",
        summary: "",
        score: 0.9,
        url: "/events/202",
      },
    ],
  },
}

async function renderSearch(language = "en") {
  const i18n = createInstance()
  await i18n.init({
    lng: language,
    resources: { en: { common: enCommon }, ru: { common: ruCommon } },
  })
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  })
  clients.push(client)
  const rootRoute = createRootRoute({
    component: () => (
      <>
        <SearchDialog />
        <Outlet />
      </>
    ),
  })
  const routes = ["/", "/news/$id", "/events/$id"].map((path) =>
    createRoute({ getParentRoute: () => rootRoute, path, component: () => null })
  )
  const router = createRouter({
    routeTree: rootRoute.addChildren(routes),
    history: createMemoryHistory({ initialEntries: ["/"] }),
  })
  await router.load()
  const view = render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={client}>
        <RouterProvider router={router as never} />
      </QueryClientProvider>
    </I18nextProvider>
  )
  return { ...view, router, client }
}

function openSearch() {
  fireEvent.keyDown(document, { key: "k", ctrlKey: true })
  return screen.getByRole("textbox")
}

async function showResults() {
  const input = openSearch()
  fireEvent.change(input, { target: { value: "physics" } })
  await screen.findByRole("button", { name: "Physics seminar" })
  return input
}

function press(input: HTMLElement, key: string) {
  const event = createEvent.keyDown(input, { key, cancelable: true })
  fireEvent(input, event)
  return event
}

describe("SearchDialog user behavior", () => {
  beforeEach(() => {
    localStorage.clear()
    apiGet.mockReset().mockResolvedValue({ data: response })
  })

  afterEach(() => {
    cleanup()
    clients.splice(0).forEach((client) => client.clear())
    vi.useRealTimers()
    vi.restoreAllMocks()
    localStorage.clear()
  })

  it("waits for the 200ms typing pause and sends only the latest eligible query", async () => {
    await renderSearch()
    vi.useFakeTimers()
    const input = openSearch()
    expect(apiGet).not.toHaveBeenCalled()
    fireEvent.change(input, { target: { value: "p" } })
    await act(() => vi.advanceTimersByTimeAsync(200))
    expect(apiGet).not.toHaveBeenCalled()

    fireEvent.change(input, { target: { value: "ph" } })
    expect(screen.getByText("Use the arrow keys to navigate")).toBeInTheDocument()
    expect(screen.queryByText("No matching results")).not.toBeInTheDocument()
    await act(() => vi.advanceTimersByTimeAsync(199))
    expect(apiGet).not.toHaveBeenCalled()
    fireEvent.change(input, { target: { value: "physics" } })
    await act(() => vi.advanceTimersByTimeAsync(199))
    expect(apiGet).not.toHaveBeenCalled()
    await act(() => vi.advanceTimersByTimeAsync(1))
    expect(apiGet).toHaveBeenCalledTimes(1)
    expect(apiGet).toHaveBeenCalledWith("/search", {
      params: { q: "physics", type: "all", limit: 8 },
    })
    await act(() => vi.advanceTimersByTimeAsync(1))
    expect(screen.getByRole("button", { name: "Physics seminar" })).toBeInTheDocument()
  })

  it("does not submit a pending query after the dialog closes", async () => {
    await renderSearch()
    vi.useFakeTimers()
    fireEvent.change(openSearch(), { target: { value: "physics" } })
    fireEvent.keyDown(document, { key: "Escape" })
    await act(() => vi.advanceTimersByTimeAsync(250))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(apiGet).not.toHaveBeenCalled()
    expect(openSearch()).toHaveValue("")
  })

  it("ignores an unmodified K and displays the Windows shortcut", async () => {
    vi.spyOn(navigator, "platform", "get").mockReturnValue("Win32")
    await renderSearch()
    fireEvent.keyDown(document, { key: "k" })
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    openSearch()
    expect(screen.getByText("Ctrl+K")).toBeInTheDocument()
    expect(screen.queryByText("⌘+K")).not.toBeInTheDocument()
  })

  it.each(["close", "unmount"])(
    "safely drains a queued focus frame after %s before the frame runs",
    async (interruption) => {
      const view = await renderSearch()
      vi.useFakeTimers()
      const input = openSearch()
      const focus = vi.spyOn(input, "focus")
      if (interruption === "close") {
        fireEvent.keyDown(document, { key: "Escape" })
      } else {
        view.unmount()
      }
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
      await act(() => vi.advanceTimersToNextFrame())
      expect(focus).not.toHaveBeenCalled()
    }
  )

  it.each([
    ["en", "Search", "Search the application", "Search…", "Clear search"],
    ["ru", "Поиск", "Поиск по приложению", "Поиск…", "Очистить поиск"],
  ])("shows the existing %s translations", async (language, title, label, placeholder, clear) => {
    await renderSearch(language)
    const input = openSearch()
    expect(screen.getByRole("dialog", { name: title })).toBeInTheDocument()
    expect(screen.getByRole("textbox", { name: label })).toHaveAttribute("placeholder", placeholder)
    fireEvent.change(input, { target: { value: "p" } })
    expect(screen.getByRole("button", { name: clear })).toBeInTheDocument()
  })

  it("prevents arrow-key scrolling and Enter submission only for the selected result", async () => {
    const { router } = await renderSearch()
    const input = await showResults()
    expect(press(input, "Enter").defaultPrevented).toBe(false)
    expect(router.state.location.pathname).toBe("/")
    expect(press(input, "ArrowDown").defaultPrevented).toBe(true)
    expect(press(input, "ArrowUp").defaultPrevented).toBe(true)
    expect(press(input, "Enter").defaultPrevented).toBe(false)
    press(input, "ArrowDown")
    expect(press(input, "Tab").defaultPrevented).toBe(false)
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(router.state.location.pathname).toBe("/")
    expect(press(input, "Enter").defaultPrevented).toBe(true)
    await waitFor(() => expect(router.state.location.pathname).toBe("/events/202"))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("clears the active result after closing and reopening a cached search", async () => {
    const { router } = await renderSearch()
    const input = await showResults()
    press(input, "ArrowDown")
    press(input, "ArrowDown")
    fireEvent.keyDown(document, { key: "Escape" })
    fireEvent.change(openSearch(), { target: { value: "physics" } })
    await screen.findByRole("button", { name: "Physics seminar" })
    expect(press(screen.getByRole("textbox"), "Enter").defaultPrevented).toBe(false)
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(router.state.location.pathname).toBe("/")
  })

  it("clears the keyboard selection immediately when Clear search is pressed", async () => {
    const { router } = await renderSearch()
    const input = await showResults()
    vi.useFakeTimers()
    press(input, "ArrowDown")
    fireEvent.click(screen.getByRole("button", { name: "Clear search" }))
    expect(input).toHaveValue("")
    expect(press(input, "Enter").defaultPrevented).toBe(false)
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(router.state.location.pathname).toBe("/")
    expect(localStorage.getItem(RECENT_SEARCHES_KEY)).toBeNull()
    await act(() => vi.advanceTimersByTimeAsync(201))
    expect(router.state.location.pathname).toBe("/")
    expect(screen.queryByRole("button", { name: "Physics seminar" })).not.toBeInTheDocument()
    expect(screen.getByText("Use the arrow keys to navigate")).toBeInTheDocument()
  })

  it("cannot reselect a stale result while the cleared query is still debouncing", async () => {
    const { router } = await renderSearch()
    const input = await showResults()
    vi.useFakeTimers()
    press(input, "ArrowDown")
    fireEvent.click(screen.getByRole("button", { name: "Clear search" }))
    press(input, "ArrowDown")
    expect(press(input, "Enter").defaultPrevented).toBe(false)
    expect(screen.queryByRole("button", { name: "Physics seminar" })).not.toBeInTheDocument()
    await act(() => vi.advanceTimersByTimeAsync(201))
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(router.state.location.pathname).toBe("/")
    expect(localStorage.getItem(RECENT_SEARCHES_KEY)).toBeNull()
  })

  it("starts a recent search without restoring the selection from before Clear", async () => {
    localStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(["physics"]))
    const { router } = await renderSearch()
    const input = await showResults()
    press(input, "ArrowDown")
    fireEvent.click(screen.getByRole("button", { name: "Clear search" }))
    fireEvent.click(screen.getByRole("button", { name: "physics" }))
    await screen.findByRole("button", { name: "Physics seminar" })
    expect(press(input, "Enter").defaultPrevented).toBe(false)
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(router.state.location.pathname).toBe("/")
  })

  it("keeps keyboard navigation safe when a refresh removes the selected results", async () => {
    const { client, router } = await renderSearch()
    const input = await showResults()
    press(input, "ArrowDown")
    press(input, "ArrowDown")
    apiGet.mockResolvedValue({ data: { query: "physics", results: { news: [], events: [] } } })
    await act(() => client.invalidateQueries({ queryKey: ["search", "physics"] }))
    await screen.findByText("No matching results")
    expect(press(input, "ArrowUp").defaultPrevented).toBe(true)
    expect(press(input, "Enter").defaultPrevented).toBe(false)
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(router.state.location.pathname).toBe("/")
  })

  it("moves the selection affordance through score-ordered results", async () => {
    await renderSearch()
    const input = await showResults()
    const event = screen.getByRole("button", { name: "Physics seminar" })
    const news = screen.getByRole("button", { name: "Physics news New campus laboratory" })
    const results = [...document.querySelectorAll("[data-search-item]")]
    expect(results).toEqual([event, news])
    expect(event.querySelectorAll("p")).toHaveLength(1)
    expect(news.querySelectorAll("p")).toHaveLength(2)
    expect(event.querySelector(".lucide-arrow-right")).toHaveClass("opacity-0")
    expect(news.querySelector(".lucide-arrow-right")).toHaveClass("opacity-0")
    press(input, "ArrowDown")
    expect(event.querySelector(".lucide-arrow-right")).toHaveClass("opacity-100")
    expect(news.querySelector(".lucide-arrow-right")).toHaveClass("opacity-0")
    press(input, "ArrowDown")
    expect(event.querySelector(".lucide-arrow-right")).toHaveClass("opacity-0")
    expect(news.querySelector(".lucide-arrow-right")).toHaveClass("opacity-100")
  })

  it("caps a new saved search at five entries and replays it on reopen", async () => {
    localStorage.setItem(
      RECENT_SEARCHES_KEY,
      JSON.stringify(["one", "two", "three", "four", "five"])
    )
    const { router } = await renderSearch()
    await showResults()
    fireEvent.click(screen.getByRole("button", { name: "Physics seminar" }))
    await waitFor(() => expect(router.state.location.pathname).toBe("/events/202"))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(JSON.parse(localStorage.getItem(RECENT_SEARCHES_KEY) ?? "null")).toEqual([
      "physics",
      "one",
      "two",
      "three",
      "four",
    ])
    openSearch()
    fireEvent.click(screen.getByRole("button", { name: "physics" }))
    expect(screen.getByRole("textbox")).toHaveValue("physics")
    await screen.findByRole("button", { name: "Physics seminar" })
  })

  it("replaces the loading indicator with the empty response message", async () => {
    let resolve: (value: { data: { query: string; results: object } }) => void = () => {}
    apiGet.mockReturnValue(
      new Promise((settle) => {
        resolve = settle
      })
    )
    const { container } = await renderSearch()
    const input = openSearch()
    expect(container.querySelector(".animate-spin")).not.toBeInTheDocument()
    fireEvent.change(input, { target: { value: "unknown" } })
    await waitFor(() => expect(apiGet).toHaveBeenCalledTimes(1))
    expect(container.querySelector(".animate-spin")).toBeInTheDocument()
    expect(screen.queryByText("No matching results")).not.toBeInTheDocument()
    await act(async () =>
      resolve({ data: { query: "unknown", results: { news: [], events: [] } } })
    )
    await screen.findByText("No matching results")
    expect(container.querySelector(".animate-spin")).not.toBeInTheDocument()
  })
})
