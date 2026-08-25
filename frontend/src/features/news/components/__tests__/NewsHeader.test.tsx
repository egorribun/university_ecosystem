/**
 * Coverage tests for NewsHeader (testing session 9).
 *
 * Functions coverage was 1/8 — the inline JSX handlers (search change/clear,
 * category pills, saved filter, sort toggle, admin add) were unexercised.
 */
import { screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { NewsHeader } from "@/features/news/components/NewsHeader"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

type Props = Parameters<typeof NewsHeader>[0]

const renderHeader = async (overrides: Partial<Props> = {}) => {
  const props: Props = {
    onAddClick: vi.fn(),
    isAdmin: false,
    newsCount: 7,
    searchQuery: "",
    onSearchChange: vi.fn(),
    activeCategory: "all",
    onCategoryChange: vi.fn(),
    sortMode: "newest",
    onSortChange: vi.fn(),
    bookmarkCount: 0,
    ...overrides,
  }
  await renderWithRouter({
    ui: () => <NewsHeader {...props} />,
    authProvider: false,
  })
  return props
}

describe("NewsHeader", () => {
  it("renders the news count badge and search input", async () => {
    await renderHeader()
    expect(screen.getByText("7")).toBeInTheDocument()
    expect(screen.getByRole("textbox")).toBeInTheDocument()
  })

  it("fires onSearchChange when typing in the search field", async () => {
    const props = await renderHeader()
    await userEvent.type(screen.getByRole("textbox"), "a")
    expect(props.onSearchChange).toHaveBeenCalledWith("a")
  })

  it("clears the search via the clear button", async () => {
    const props = await renderHeader({ searchQuery: "rust" })
    const clearButton = screen.getByRole("button", { name: /clear/i })
    expect(clearButton).toHaveClass("size-11")
    await userEvent.click(clearButton)
    expect(props.onSearchChange).toHaveBeenCalledWith("")
  })

  it("changes category via the All pill and category pills", async () => {
    const props = await renderHeader({ activeCategory: "all" })
    const allPill = screen.getByRole("button", { current: "page" })
    expect(allPill).toBeInTheDocument()

    // Click a non-active category pill (any pill that is not aria-current).
    const pills = screen
      .getAllByRole("button")
      .filter((b) => b.getAttribute("aria-current") !== "page")
    expect(pills.length).toBeGreaterThan(0)
    await userEvent.click(pills[0]!)
    expect(props.onCategoryChange).toHaveBeenCalled()

    await userEvent.click(allPill)
    expect(props.onCategoryChange).toHaveBeenCalledWith("all")
  })

  it("exposes 44px category targets in a keyboard-navigable toolbar", async () => {
    await renderHeader()
    const toolbar = screen.getByRole("toolbar", { name: /filter news by category/i })
    const allButton = screen.getByRole("button", { name: /^all$/i })
    const categoryButtons = toolbar.querySelectorAll<HTMLButtonElement>("button")

    expect(allButton).toHaveClass("min-h-[44px]")
    allButton.focus()
    await userEvent.keyboard("{ArrowRight}")
    expect(categoryButtons[1]).toHaveFocus()
  })

  it("shows the saved filter only when bookmarks exist and selects it", async () => {
    const props = await renderHeader({ bookmarkCount: 3 })
    const savedPill = screen.getByText("(3)").closest("button")
    expect(savedPill).not.toBeNull()
    await userEvent.click(savedPill!)
    expect(props.onCategoryChange).toHaveBeenCalledWith("saved")
  })

  it("hides the saved filter when there are no bookmarks", async () => {
    await renderHeader({ bookmarkCount: 0 })
    expect(screen.queryByText(/\(0\)/)).not.toBeInTheDocument()
  })

  it("toggles sort mode newest -> popular and back", async () => {
    const props = await renderHeader({ sortMode: "newest" })
    const sortButton = screen.getByRole("button", { name: /sort/i })
    await userEvent.click(sortButton)
    expect(props.onSortChange).toHaveBeenCalledWith("popular")
  })

  it("toggles sort mode popular -> newest", async () => {
    const props = await renderHeader({ sortMode: "popular" })
    const sortButton = screen.getByRole("button", { name: /sort/i })
    await userEvent.click(sortButton)
    expect(props.onSortChange).toHaveBeenCalledWith("newest")
  })

  it("shows the add button for admins and fires onAddClick", async () => {
    const props = await renderHeader({ isAdmin: true })
    const addButton = document.getElementById("news-header-add-btn")
    expect(addButton).not.toBeNull()
    await userEvent.click(addButton!)
    expect(props.onAddClick).toHaveBeenCalled()
  })

  it("hides the add button for non-admins", async () => {
    await renderHeader({ isAdmin: false })
    expect(document.getElementById("news-header-add-btn")).toBeNull()
  })
})
