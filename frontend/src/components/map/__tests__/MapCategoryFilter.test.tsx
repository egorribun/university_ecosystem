import { useState } from "react"
import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

const useTranslationMock = vi.hoisted(() => vi.fn())

vi.mock("react-i18next", () => ({
  useTranslation: useTranslationMock,
}))

import { MapCategoryFilter } from "@/components/map/MapCategoryFilter"
import { MAP_CATEGORIES, type MapCategory } from "@/data/campusBuildings"

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

  it("updates a controlled selection through radio keys and keeps one tab stop", async () => {
    useTranslationMock.mockReturnValue({ t: (key: string) => key })
    const user = userEvent.setup()
    const onChange = vi.fn()

    function ControlledFilter() {
      const [active, setActive] = useState<MapCategory | "all">(MAP_CATEGORIES[0]!)
      return (
        <MapCategoryFilter
          active={active}
          onChange={(category) => {
            onChange(category)
            setActive(category)
          }}
        />
      )
    }

    render(<ControlledFilter />)

    const radios = screen.getAllByRole("radio")
    const expectSelected = (index: number) => {
      radios.forEach((radio, radioIndex) => {
        expect(radio).toHaveAttribute("aria-checked", String(radioIndex === index))
        expect(radio).toHaveAttribute("tabindex", radioIndex === index ? "0" : "-1")
      })
    }
    expectSelected(1)

    radios[1]!.focus()
    await user.keyboard("{ArrowRight}")
    expect(radios[2]).toHaveFocus()
    expectSelected(2)
    expect(onChange).toHaveBeenLastCalledWith(MAP_CATEGORIES[1])

    await user.keyboard("{ArrowDown}")
    expect(radios[3]).toHaveFocus()
    expectSelected(3)

    await user.keyboard("{ArrowUp}")
    expect(radios[2]).toHaveFocus()
    expectSelected(2)

    await user.keyboard("{ArrowLeft}")
    expect(radios[1]).toHaveFocus()
    expectSelected(1)
    expect(onChange).toHaveBeenLastCalledWith(MAP_CATEGORIES[0])

    await user.keyboard("{Home}")
    expect(radios[0]).toHaveFocus()
    expectSelected(0)

    await user.keyboard("{ArrowLeft}")
    expect(radios.at(-1)).toHaveFocus()
    expectSelected(radios.length - 1)
    expect(onChange).toHaveBeenLastCalledWith(MAP_CATEGORIES.at(-1))

    await user.keyboard("{ArrowRight}")
    expect(radios[0]).toHaveFocus()
    expectSelected(0)

    await user.keyboard("{End}")
    expect(radios.at(-1)).toHaveFocus()
    expectSelected(radios.length - 1)

    const changesBeforeUnrelatedKey = onChange.mock.calls.length
    await user.keyboard("x")
    expectSelected(radios.length - 1)
    expect(onChange).toHaveBeenCalledTimes(changesBeforeUnrelatedKey)

    radios[1]!.focus()
    await user.keyboard(" ")
    expectSelected(1)
    expect(onChange).toHaveBeenLastCalledWith(MAP_CATEGORIES[0])
  })
})

describe("MapCategoryFilter keyboard guards under DOM interference", () => {
  it("ignores category keys after external code removes the radio-group role", () => {
    useTranslationMock.mockReturnValue({ t: (key: string) => key })
    const onChange = vi.fn()
    render(<MapCategoryFilter active={MAP_CATEGORIES[0]!} onChange={onChange} />)

    const group = screen.getByRole("radiogroup")
    const radios = screen.getAllByRole("radio")
    const focusedRadio = radios[1]!
    focusedRadio.focus()
    group.removeAttribute("role")

    const keydown = new KeyboardEvent("keydown", {
      key: "ArrowRight",
      bubbles: true,
      cancelable: true,
    })
    expect(() => fireEvent(focusedRadio, keydown)).not.toThrow()
    expect(keydown.defaultPrevented).toBe(false)
    expect(focusedRadio).toHaveFocus()
    expect(radios[2]).not.toHaveFocus()
    expect(onChange).not.toHaveBeenCalled()
  })

  it("ignores category keys when external code removes the focused radio role", () => {
    useTranslationMock.mockReturnValue({ t: (key: string) => key })
    const onChange = vi.fn()
    render(<MapCategoryFilter active={MAP_CATEGORIES[0]!} onChange={onChange} />)

    const radios = screen.getAllByRole("radio")
    const focusedRadio = radios[1]!
    focusedRadio.focus()
    focusedRadio.removeAttribute("role")

    const keydown = new KeyboardEvent("keydown", {
      key: "ArrowRight",
      bubbles: true,
      cancelable: true,
    })
    expect(() => fireEvent(focusedRadio, keydown)).not.toThrow()
    expect(keydown.defaultPrevented).toBe(false)
    expect(focusedRadio).toHaveFocus()
    expect(radios[2]).not.toHaveFocus()
    expect(onChange).not.toHaveBeenCalled()
  })
})
