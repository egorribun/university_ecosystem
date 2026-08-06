import { act, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { NewsHeader } from "@/features/news/components/NewsHeader"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

type Props = Parameters<typeof NewsHeader>[0]

let intersectionCallback: IntersectionObserverCallback | undefined
let disconnectMock: ReturnType<typeof vi.fn> | undefined

class TestIntersectionObserver {
  constructor(callback: IntersectionObserverCallback) {
    intersectionCallback = callback
    disconnectMock = vi.fn()
  }

  observe() {}

  disconnect() {
    disconnectMock?.()
  }
}

const renderHeader = async (overrides: Partial<Props> = {}) => {
  const props: Props = {
    onAddClick: vi.fn(),
    isAdmin: false,
    newsCount: undefined,
    searchQuery: "",
    onSearchChange: vi.fn(),
    activeCategory: "saved",
    onCategoryChange: vi.fn(),
    sortMode: "popular",
    onSortChange: vi.fn(),
    bookmarkCount: 2,
    ...overrides,
  }

  const result = await renderWithRouter({
    ui: () => <NewsHeader {...props} />,
    authProvider: false,
  })
  return { ...result, props }
}

afterEach(() => {
  vi.unstubAllGlobals()
  intersectionCallback = undefined
  disconnectMock = undefined
})

describe("NewsHeader — sticky observer and optional branches", () => {
  it("tracks sticky state and disconnects the observer on unmount", async () => {
    vi.stubGlobal("IntersectionObserver", TestIntersectionObserver)
    const { container, unmount } = await renderHeader()
    const stickyCategories = container.querySelector(".news-sticky-categories")

    expect(stickyCategories).toHaveAttribute("data-stuck", "false")
    expect(screen.getByRole("heading")).toBeInTheDocument()

    act(() => {
      intersectionCallback?.([], {} as IntersectionObserver)
    })
    expect(stickyCategories).toHaveAttribute("data-stuck", "false")

    act(() => {
      intersectionCallback?.(
        [{ isIntersecting: false } as IntersectionObserverEntry],
        {} as IntersectionObserver
      )
    })
    expect(stickyCategories).toHaveAttribute("data-stuck", "true")

    act(() => {
      intersectionCallback?.(
        [{ isIntersecting: true } as IntersectionObserverEntry],
        {} as IntersectionObserver
      )
    })
    expect(stickyCategories).toHaveAttribute("data-stuck", "false")

    unmount()
    expect(disconnectMock).toHaveBeenCalledOnce()
  })

  it("renders the optional category/count states and forwards their handlers", async () => {
    const { props } = await renderHeader({ newsCount: 0, activeCategory: "all" })

    expect(screen.getByText("0")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /saved/i })).toBeInTheDocument()

    await act(async () => {
      screen.getByRole("button", { name: /saved/i }).click()
      screen.getByRole("button", { name: /sort: popular/i }).click()
    })

    expect(props.onCategoryChange).toHaveBeenCalledWith("saved")
    expect(props.onSortChange).toHaveBeenCalledWith("newest")
  })

  it("marks an active category and forwards its exact identifier", async () => {
    const { props } = await renderHeader({ activeCategory: "education" })
    const activeCategory = screen.getAllByRole("button", { current: "page" })[0]

    expect(activeCategory).toBeDefined()
    expect(activeCategory).toHaveAttribute("aria-current", "page")
    await act(async () => {
      activeCategory?.click()
    })

    expect(props.onCategoryChange).toHaveBeenCalledWith("education")
  })
})
