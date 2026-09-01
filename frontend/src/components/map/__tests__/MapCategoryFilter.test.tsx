import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

const useTranslationMock = vi.hoisted(() => vi.fn())

vi.mock("react-i18next", () => ({
  useTranslation: useTranslationMock,
}))

import { MapCategoryFilter } from "@/components/map/MapCategoryFilter"
import { MAP_CATEGORIES } from "@/data/campusBuildings"

describe("MapCategoryFilter", () => {
  it("renders the complete localized radio contract and marks only the active category", () => {
    useTranslationMock.mockReturnValue({ t: (key: string) => `translated:${key}` })
    const onChange = vi.fn()

    render(<MapCategoryFilter active={MAP_CATEGORIES[0]!} onChange={onChange} />)

    expect(useTranslationMock).toHaveBeenCalledWith("map")
    const radios = screen.getAllByRole("radio")
    expect(radios).toHaveLength(MAP_CATEGORIES.length + 1)
    expect(radios[0]).toHaveTextContent("translated:categories.all")
    expect(radios[0]).not.toHaveAttribute("data-active")
    expect(radios[1]).toHaveTextContent(`translated:categories.${MAP_CATEGORIES[0]}`)
    expect(radios[1]).toHaveAttribute("data-active", "true")
    expect(radios[1]).toHaveAttribute("aria-checked", "true")
    expect(radios.slice(2).every((radio) => radio.getAttribute("data-active") === null)).toBe(true)
    expect(radios.slice(2).every((radio) => radio.getAttribute("aria-checked") === "false")).toBe(
      true
    )
  })

  it("reports the selected category", async () => {
    useTranslationMock.mockReturnValue({ t: (key: string) => key })
    const onChange = vi.fn()
    render(<MapCategoryFilter active="all" onChange={onChange} />)

    await userEvent.click(screen.getAllByRole("radio")[1]!)

    expect(onChange).toHaveBeenCalledOnce()
    expect(onChange).not.toHaveBeenCalledWith("all")
  })
})
