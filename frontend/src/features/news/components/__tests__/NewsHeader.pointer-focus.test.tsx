import { createEvent, fireEvent, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { NewsHeader } from "@/features/news/components/NewsHeader"
import type { NewsCategory } from "@/features/news/categories"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

describe("NewsHeader mouse-focus regression", () => {
  it("keeps pointer activation focused without requesting viewport scrolling", async () => {
    const onCategoryChange = vi.fn<(category: NewsCategory | "all" | "saved") => void>()
    await renderWithRouter({
      ui: () => (
        <NewsHeader
          onAddClick={vi.fn()}
          isAdmin={false}
          newsCount={7}
          searchQuery=""
          onSearchChange={vi.fn()}
          activeCategory="all"
          onCategoryChange={onCategoryChange}
          sortMode="newest"
          onSortChange={vi.fn()}
        />
      ),
      authProvider: false,
    })

    const all = screen.getByRole("button", { name: /^all$/i })
    const science = screen.getByRole("button", { name: /science/i })
    const toolbar = screen.getByRole("toolbar", { name: /filter news by category/i })
    const focus = vi.spyOn(science, "focus")

    const secondaryDown = createEvent.mouseDown(science, { button: 2 })
    fireEvent(science, secondaryDown)
    expect(secondaryDown.defaultPrevented).toBe(false)

    all.focus()
    await userEvent.click(science)

    expect(onCategoryChange).toHaveBeenCalledWith("science")
    expect(science).toHaveFocus()
    expect(focus).toHaveBeenCalledWith({ preventScroll: true })

    all.focus()
    await userEvent.keyboard("{ArrowRight}")
    expect(screen.getByRole("button", { name: /education/i })).toHaveFocus()
    expect(toolbar).toContainElement(science)
  })
})
