import { render, screen, fireEvent } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { Select, type SelectOption } from "../Select"

/**
 * Select — accessible WAI-ARIA listbox (pure props-driven, no API / context).
 *
 * framer-motion is mocked (the established per-file convention, e.g.
 * NotificationsBell.test.tsx) so `AnimatePresence` renders children
 * synchronously and `m.div` is a plain element — the listbox + options appear
 * in the DOM the instant the trigger opens, with no LazyMotion ancestor and no
 * animation timing.
 *
 * react-i18next is mocked so the default-placeholder branch
 * (`placeholder ?? t("select.placeholder")`) resolves to a known string.
 */

vi.mock("framer-motion", () => {
  const motionComponent = (Tag: string) => {
    const Component = ({
      children,
      ...props
    }: React.ComponentProps<"div"> & { [key: string]: unknown }) => {
      const filtered = { ...props }
      for (const prop of [
        "initial",
        "animate",
        "exit",
        "variants",
        "transition",
        "whileHover",
        "whileTap",
        "whileFocus",
        "layout",
        "layoutId",
      ]) {
        delete filtered[prop]
      }
      const Element = Tag as React.ElementType
      return <Element {...filtered}>{children}</Element>
    }
    Component.displayName = `Motion(${Tag})`
    return Component as unknown as React.ComponentType<unknown>
  }
  const proxy = { div: motionComponent("div"), button: motionComponent("button") }
  return {
    AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    LazyMotion: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    MotionConfig: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    domAnimation: {},
    domMax: {},
    motion: proxy,
    m: proxy,
    useReducedMotion: () => false,
  }
})

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => (key === "select.placeholder" ? "Select an option" : key),
  }),
}))

const OPTIONS: SelectOption[] = [
  { value: "apple", label: "Apple" },
  { value: "banana", label: "Banana" },
  { value: "cherry", label: "Cherry" },
]

function renderSelect(props: Partial<React.ComponentProps<typeof Select>> = {}) {
  return render(<Select id="sel" options={OPTIONS} {...props} />)
}

const trigger = () => screen.getByRole("combobox")
const optionId = (index: number) => `sel-option-${index}`

afterEach(() => {
  vi.restoreAllMocks()
})

describe("Select — rendering & ARIA", () => {
  it("renders the i18n default placeholder when no value or placeholder prop", () => {
    renderSelect()
    expect(trigger()).toHaveTextContent("Select an option")
  })

  it("renders an explicit placeholder over the i18n default", () => {
    renderSelect({ placeholder: "Pick a fruit" })
    expect(trigger()).toHaveTextContent("Pick a fruit")
  })

  it("renders the selected option's label when value matches", () => {
    renderSelect({ value: "banana" })
    expect(trigger()).toHaveTextContent("Banana")
  })

  it("exposes the closed-state combobox ARIA contract", () => {
    renderSelect()
    const btn = trigger()
    expect(btn).toHaveAttribute("aria-haspopup", "listbox")
    expect(btn).toHaveAttribute("aria-expanded", "false")
    expect(btn).toHaveAttribute("aria-controls", "sel-listbox")
    expect(btn).not.toHaveAttribute("aria-activedescendant")
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
  })

  it("forwards aria-label to both the trigger and the open listbox", () => {
    renderSelect({ "aria-label": "Fruit picker" })
    const btn = trigger()
    expect(btn).toHaveAttribute("aria-label", "Fruit picker")
    fireEvent.click(btn)
    expect(screen.getByRole("listbox")).toHaveAttribute("aria-label", "Fruit picker")
  })

  it("marks the option matching the current value as aria-selected", () => {
    renderSelect({ value: "cherry" })
    fireEvent.click(trigger())
    const options = screen.getAllByRole("option")
    expect(options[2]!).toHaveAttribute("aria-selected", "true")
    expect(options[0]!).toHaveAttribute("aria-selected", "false")
  })

  it("applies the error variant styling", () => {
    renderSelect({ error: true })
    expect(trigger().className).toContain("border-error-text")
  })
})

describe("Select — open / close", () => {
  it("opens on trigger click and renders every option", () => {
    renderSelect()
    fireEvent.click(trigger())
    expect(trigger()).toHaveAttribute("aria-expanded", "true")
    expect(screen.getByRole("listbox")).toBeInTheDocument()
    expect(screen.getAllByRole("option")).toHaveLength(OPTIONS.length)
  })

  it("focuses the first option when opening with no selection", () => {
    renderSelect()
    fireEvent.click(trigger())
    expect(trigger()).toHaveAttribute("aria-activedescendant", optionId(0))
  })

  it("focuses the selected option when opening with a value", () => {
    renderSelect({ value: "cherry" })
    fireEvent.click(trigger())
    expect(trigger()).toHaveAttribute("aria-activedescendant", optionId(2))
  })

  it("closes on a second trigger click", () => {
    renderSelect()
    const btn = trigger()
    fireEvent.click(btn)
    fireEvent.click(btn)
    expect(btn).toHaveAttribute("aria-expanded", "false")
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
  })

  it("closes on Escape", () => {
    renderSelect()
    const btn = trigger()
    fireEvent.click(btn)
    fireEvent.keyDown(btn, { key: "Escape" })
    expect(btn).toHaveAttribute("aria-expanded", "false")
  })

  it("closes on an outside mousedown", () => {
    renderSelect()
    fireEvent.click(trigger())
    expect(screen.getByRole("listbox")).toBeInTheDocument()
    fireEvent.mouseDown(document.body)
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
  })

  it("closes on Tab while open", () => {
    renderSelect()
    const btn = trigger()
    fireEvent.click(btn)
    fireEvent.keyDown(btn, { key: "Tab" })
    expect(btn).toHaveAttribute("aria-expanded", "false")
  })
})

describe("Select — selection", () => {
  it("calls onValueChange and closes when an option is chosen via mousedown", () => {
    const onValueChange = vi.fn()
    renderSelect({ onValueChange })
    fireEvent.click(trigger())
    fireEvent.mouseDown(screen.getByText("Banana"))
    expect(onValueChange).toHaveBeenCalledWith("banana")
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
  })

  it("sets the active option on mouse enter", () => {
    renderSelect()
    fireEvent.click(trigger())
    fireEvent.mouseEnter(screen.getByText("Cherry"))
    expect(trigger()).toHaveAttribute("aria-activedescendant", optionId(2))
  })
})

describe("Select — keyboard", () => {
  it("opens on Enter when closed, then selects the active option on Enter", () => {
    const onValueChange = vi.fn()
    renderSelect({ onValueChange })
    const btn = trigger()
    fireEvent.keyDown(btn, { key: "Enter" })
    expect(btn).toHaveAttribute("aria-expanded", "true")
    // active is option 0 ("apple") on open with no selection
    fireEvent.keyDown(btn, { key: "Enter" })
    expect(onValueChange).toHaveBeenCalledWith("apple")
  })

  it("opens on Space, then selects the active option on Space", () => {
    const onValueChange = vi.fn()
    renderSelect({ onValueChange })
    const btn = trigger()
    fireEvent.keyDown(btn, { key: " " })
    expect(btn).toHaveAttribute("aria-expanded", "true")
    fireEvent.keyDown(btn, { key: " " })
    expect(onValueChange).toHaveBeenCalledWith("apple")
  })

  it("opens on ArrowDown when closed", () => {
    renderSelect()
    const btn = trigger()
    fireEvent.keyDown(btn, { key: "ArrowDown" })
    expect(btn).toHaveAttribute("aria-expanded", "true")
  })

  it("opens on ArrowUp when closed", () => {
    renderSelect()
    const btn = trigger()
    fireEvent.keyDown(btn, { key: "ArrowUp" })
    expect(btn).toHaveAttribute("aria-expanded", "true")
  })

  it("navigates down then up, clamping at the bounds", () => {
    renderSelect()
    const btn = trigger()
    fireEvent.click(btn) // active 0
    fireEvent.keyDown(btn, { key: "ArrowDown" }) // 1
    fireEvent.keyDown(btn, { key: "ArrowDown" }) // 2
    fireEvent.keyDown(btn, { key: "ArrowDown" }) // clamp at 2 (last)
    expect(btn).toHaveAttribute("aria-activedescendant", optionId(2))
    fireEvent.keyDown(btn, { key: "ArrowUp" }) // 1
    fireEvent.keyDown(btn, { key: "ArrowUp" }) // 0
    fireEvent.keyDown(btn, { key: "ArrowUp" }) // clamp at 0 (first)
    expect(btn).toHaveAttribute("aria-activedescendant", optionId(0))
  })

  it("jumps to last on End and first on Home", () => {
    renderSelect()
    const btn = trigger()
    fireEvent.click(btn)
    fireEvent.keyDown(btn, { key: "End" })
    expect(btn).toHaveAttribute("aria-activedescendant", optionId(2))
    fireEvent.keyDown(btn, { key: "Home" })
    expect(btn).toHaveAttribute("aria-activedescendant", optionId(0))
  })

  it("type-ahead focuses the first option whose label matches", () => {
    renderSelect()
    const btn = trigger()
    fireEvent.click(btn)
    fireEvent.keyDown(btn, { key: "b" })
    expect(btn).toHaveAttribute("aria-activedescendant", optionId(1))
  })

  it("type-ahead with no match leaves the active option unchanged", () => {
    renderSelect()
    const btn = trigger()
    fireEvent.click(btn) // active 0
    fireEvent.keyDown(btn, { key: "z" })
    expect(btn).toHaveAttribute("aria-activedescendant", optionId(0))
  })

  it("resets the type-ahead buffer after the 500ms timeout", () => {
    vi.useFakeTimers()
    try {
      renderSelect()
      const btn = trigger()
      fireEvent.click(btn)
      fireEvent.keyDown(btn, { key: "c" }) // → Cherry (2)
      expect(btn).toHaveAttribute("aria-activedescendant", optionId(2))
      vi.advanceTimersByTime(500) // buffer reset timer fires
      // Buffer cleared → "b" matches from scratch (not "cb", which has no match)
      fireEvent.keyDown(btn, { key: "b" })
      expect(btn).toHaveAttribute("aria-activedescendant", optionId(1))
    } finally {
      vi.useRealTimers()
    }
  })
})

describe("Select — disabled", () => {
  it("renders a disabled trigger and ignores click + keydown", () => {
    const onValueChange = vi.fn()
    renderSelect({ disabled: true, onValueChange })
    const btn = trigger()
    expect(btn).toBeDisabled()
    fireEvent.click(btn)
    expect(btn).toHaveAttribute("aria-expanded", "false")
    fireEvent.keyDown(btn, { key: "Enter" })
    expect(btn).toHaveAttribute("aria-expanded", "false")
    expect(onValueChange).not.toHaveBeenCalled()
  })
})
