import { render, screen, fireEvent } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { Select, type SelectOption } from "../Select"

const translationNamespaceSpy = vi.hoisted(() => vi.fn())
const motionPropsSpy = vi.hoisted(() => vi.fn())

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
      motionPropsSpy(props)
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
  useTranslation: (namespace: string) => {
    translationNamespaceSpy(namespace)
    return {
      t: (key: string) => (key === "select.placeholder" ? "Select an option" : key),
    }
  },
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
  translationNamespaceSpy.mockClear()
  motionPropsSpy.mockClear()
})

describe("Select — rendering & ARIA", () => {
  it("renders the i18n default placeholder when no value or placeholder prop", () => {
    renderSelect()
    expect(trigger()).toHaveTextContent("Select an option")
    expect(translationNamespaceSpy).toHaveBeenCalledWith("common")
  })

  it("renders an explicit placeholder over the i18n default", () => {
    renderSelect({ placeholder: "Pick a fruit" })
    expect(trigger()).toHaveTextContent("Pick a fruit")
  })

  it("renders the selected option's label when value matches", () => {
    renderSelect({ value: "banana" })
    expect(trigger()).toHaveTextContent("Banana")
  })

  it("uses the first selected option as the initial active descendant", () => {
    renderSelect({ value: "apple" })
    fireEvent.click(trigger())
    expect(trigger()).toHaveAttribute("aria-activedescendant", optionId(0))
  })

  it("exposes the closed-state combobox ARIA contract", () => {
    renderSelect()
    const btn = trigger()
    expect(btn).toHaveAttribute("id", "sel-trigger")
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

  it("keeps trigger, listbox, and option identifiers stable across an id change", () => {
    const view = renderSelect()
    fireEvent.click(trigger())
    expect(screen.getByRole("listbox")).toHaveAttribute("id", "sel-listbox")
    expect(screen.getByRole("option", { name: "Apple" })).toHaveAttribute("id", optionId(0))

    view.rerender(<Select id="next" options={OPTIONS} />)
    expect(trigger()).toHaveAttribute("id", "next-trigger")
    expect(screen.getByRole("listbox")).toHaveAttribute("id", "next-listbox")
    expect(screen.getByRole("option", { name: "Apple" })).toHaveAttribute("id", "next-option-0")
  })

  it("renders every state and layout class used by the design contract", () => {
    const view = renderSelect({ disabled: true })
    const closed = trigger()
    expect(closed.parentElement).toHaveClass("relative", "w-full")
    expect(closed.className).toContain("flex min-h-12 w-full")
    expect(closed.className).toContain("border-glass-border bg-glass-bg")
    expect(closed.className).toContain("hover:border-brand/(--opacity-medium)")
    expect(closed.className).toContain("focus:outline-none focus:ring-4")
    expect(closed.className).toContain("cursor-not-allowed opacity-medium grayscale")
    expect(closed.className).toContain("text-text-tertiary")
    view.rerender(<Select id="sel" options={OPTIONS} error />)
    expect(trigger().className).toContain("border-error-text bg-error-bg")

    view.rerender(<Select id="sel" options={OPTIONS} value="apple" />)
    fireEvent.click(trigger())
    const opened = trigger()
    expect(opened.className).toContain("border-brand ring-4 ring-brand/(--opacity-subtle)")
    expect(opened.className).toContain("shadow-glow-primary")
    expect(opened.querySelector("svg")).toHaveClass("h-4", "w-4", "rotate-180")
    expect(screen.getByRole("listbox").className).toContain("absolute z-dropdown")
    expect(screen.getByRole("listbox").className).toContain("p-1.5")
    const options = screen.getAllByRole("option")
    expect(options[0]!.className).toContain("bg-brand text-inverse-text shadow-sm")
    fireEvent.mouseEnter(options[1]!)
    expect(options[1]!.className).toContain("bg-brand/(--opacity-subtle) text-brand")
    expect(options[2]!.className).toContain("text-text-primary hover:bg-brand/(--opacity-subtle)")

    fireEvent.click(opened)
    expect(opened.querySelector("svg")).not.toHaveClass("rotate-180")
  })

  it("preserves motion and keyboard-focus contracts for the listbox", () => {
    renderSelect()
    fireEvent.click(trigger())
    const listbox = screen.getByRole("listbox")
    expect(listbox).toHaveAttribute("tabindex", "-1")
    for (const option of screen.getAllByRole("option")) {
      expect(option).toHaveAttribute("tabindex", "-1")
    }
    const motionProps = motionPropsSpy.mock.calls.at(-1)?.[0] as Record<string, unknown>
    expect(motionProps).toEqual(
      expect.objectContaining({
        initial: { opacity: 0, y: -10, scale: 0.98 },
        animate: { opacity: 1, y: 4, scale: 1 },
        exit: { opacity: 0, y: -10, scale: 0.98 },
        transition: { duration: 0.2, ease: [0.16, 1, 0.3, 1] },
      })
    )
  })
})

describe("Select — open / close", () => {
  it("opens on trigger click and renders every option", () => {
    renderSelect()
    fireEvent.click(trigger())
    expect(trigger()).toHaveAttribute("aria-expanded", "true")
    expect(screen.getByRole("listbox")).toBeInTheDocument()
    const options = screen.getAllByRole("option")
    expect(options).toHaveLength(OPTIONS.length)
    for (const option of options) {
      expect(option).toHaveClass("min-h-11")
    }
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
    expect(btn).not.toHaveAttribute("aria-activedescendant")
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
  })

  it("closes on Escape", () => {
    renderSelect()
    const btn = trigger()
    fireEvent.click(btn)
    fireEvent.keyDown(btn, { key: "Escape" })
    expect(btn).toHaveAttribute("aria-expanded", "false")
    expect(btn).not.toHaveAttribute("aria-activedescendant")
  })

  it("closes on an outside mousedown", () => {
    renderSelect()
    fireEvent.click(trigger())
    expect(screen.getByRole("listbox")).toBeInTheDocument()
    fireEvent.mouseDown(document.body)
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
    expect(trigger()).not.toHaveAttribute("aria-activedescendant")
  })

  it("does not close on a mousedown inside the select container", () => {
    renderSelect()
    const btn = trigger()
    fireEvent.click(btn)
    fireEvent.mouseDown(screen.getByRole("listbox"))
    expect(screen.getByRole("listbox")).toBeInTheDocument()
  })

  it("closes on Tab while open", () => {
    renderSelect()
    const btn = trigger()
    fireEvent.click(btn)
    fireEvent.keyDown(btn, { key: "Tab" })
    expect(btn).toHaveAttribute("aria-expanded", "false")
    expect(btn).not.toHaveAttribute("aria-activedescendant")
  })

  it("does not prevent default for closed-only navigation keys", () => {
    renderSelect()
    const btn = trigger()
    for (const key of ["Home", "End", "Escape", "Tab"]) {
      const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true })
      const preventDefault = vi.spyOn(event, "preventDefault")
      fireEvent(btn, event)
      expect(preventDefault).not.toHaveBeenCalled()
    }
  })

  it("registers one outside listener and removes that exact listener on unmount", () => {
    const add = vi.spyOn(document, "addEventListener")
    const remove = vi.spyOn(document, "removeEventListener")
    const view = renderSelect()
    expect(add.mock.calls.filter(([event]) => event === "mousedown")).toHaveLength(0)
    fireEvent.click(trigger())
    const registration = add.mock.calls.find(([event]) => event === "mousedown")
    expect(registration).toBeDefined()
    expect(add.mock.calls.filter(([event]) => event === "mousedown")).toHaveLength(1)
    view.rerender(<Select id="sel" options={OPTIONS} />)
    expect(add.mock.calls.filter(([event]) => event === "mousedown")).toHaveLength(1)
    view.unmount()
    expect(remove).toHaveBeenCalledWith("mousedown", registration![1])
  })

  it("scrolls the active option with nearest-block behavior and follows id changes", () => {
    const scrollIntoView = vi.fn()
    const getElementById = vi.spyOn(document, "getElementById")
    const original = HTMLElement.prototype.scrollIntoView
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoView,
    })
    try {
      const view = renderSelect()
      expect(getElementById).not.toHaveBeenCalled()
      fireEvent.click(trigger())
      expect(scrollIntoView).toHaveBeenCalledWith({ block: "nearest" })
      scrollIntoView.mockClear()
      view.rerender(<Select id="next" options={OPTIONS} />)
      expect(scrollIntoView).toHaveBeenCalledWith({ block: "nearest" })
    } finally {
      Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
        configurable: true,
        value: original,
      })
    }
  })

  it("does not throw when the active option is no longer mounted", () => {
    const getElementById = vi.spyOn(document, "getElementById").mockReturnValue(null)

    expect(() => {
      renderSelect()
      fireEvent.click(trigger())
    }).not.toThrow()
    expect(getElementById).toHaveBeenCalledWith(optionId(0))
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

  it("prevents the option mousedown from blurring the trigger", () => {
    renderSelect()
    fireEvent.click(trigger())
    const event = new MouseEvent("mousedown", { bubbles: true, cancelable: true })
    const preventDefault = vi.spyOn(event, "preventDefault")
    fireEvent(screen.getByText("Banana"), event)
    expect(preventDefault).toHaveBeenCalledOnce()
  })

  it("sets the active option on mouse enter", () => {
    renderSelect()
    fireEvent.click(trigger())
    fireEvent.mouseEnter(screen.getByText("Cherry"))
    expect(trigger()).toHaveAttribute("aria-activedescendant", optionId(2))
  })

  it("does not require a callback when selecting a valid option", () => {
    renderSelect()
    fireEvent.click(trigger())
    expect(() => fireEvent.mouseDown(screen.getByText("Banana"))).not.toThrow()
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
  })

  it("uses the latest options and callback after a rerender", () => {
    const first = vi.fn()
    const second = vi.fn()
    const nextOptions = [
      { value: "kiwi", label: "Kiwi" },
      { value: "mango", label: "Mango" },
      { value: "pear", label: "Pear" },
    ]
    const view = renderSelect({ onValueChange: first })
    view.rerender(<Select id="sel" options={nextOptions} value="mango" onValueChange={second} />)
    fireEvent.click(trigger())
    expect(trigger()).toHaveAttribute("aria-activedescendant", "sel-option-1")
    fireEvent.mouseDown(screen.getByRole("option", { name: "Mango" }))
    expect(first).not.toHaveBeenCalled()
    expect(second).toHaveBeenCalledWith("mango")
  })

  it("does not select a stale active index after options are removed", () => {
    const onValueChange = vi.fn()
    const view = renderSelect({ onValueChange })
    const btn = trigger()
    fireEvent.click(btn)
    fireEvent.keyDown(btn, { key: "ArrowDown" })
    fireEvent.keyDown(btn, { key: "ArrowDown" })

    expect(() => {
      view.rerender(<Select id="sel" options={[]} onValueChange={onValueChange} />)
    }).not.toThrow()
    expect(btn).toHaveAttribute("aria-expanded", "true")

    fireEvent.keyDown(btn, { key: "Enter" })
    expect(onValueChange).not.toHaveBeenCalled()
    expect(btn).toHaveAttribute("aria-expanded", "true")
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

  it("does not select while closed and prevents default for Enter", () => {
    const onValueChange = vi.fn()
    renderSelect({ onValueChange })
    const btn = trigger()
    const event = new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true })
    const preventDefault = vi.spyOn(event, "preventDefault")
    fireEvent(btn, event)
    expect(preventDefault).toHaveBeenCalledOnce()
    expect(onValueChange).not.toHaveBeenCalled()
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

  it("prevents default for every handled navigation key", () => {
    renderSelect()
    const btn = trigger()
    fireEvent.click(btn)
    for (const key of ["ArrowDown", "ArrowUp", "Home", "End"]) {
      const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true })
      const preventDefault = vi.spyOn(event, "preventDefault")
      fireEvent(btn, event)
      expect(preventDefault).toHaveBeenCalledOnce()
    }
    const escape = new KeyboardEvent("keydown", {
      key: "Escape",
      bubbles: true,
      cancelable: true,
    })
    const preventEscape = vi.spyOn(escape, "preventDefault")
    fireEvent(btn, escape)
    expect(preventEscape).toHaveBeenCalledOnce()
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
    expect(btn).toHaveAttribute("aria-activedescendant", optionId(1))
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

  it("moves to an index-zero type-ahead match from another active option", () => {
    renderSelect({ value: "banana" })
    const btn = trigger()
    fireEvent.click(btn)
    expect(btn).toHaveAttribute("aria-activedescendant", optionId(1))
    fireEvent.keyDown(btn, { key: "a" })
    expect(btn).toHaveAttribute("aria-activedescendant", optionId(0))
  })

  it("matches the first option at index zero", () => {
    renderSelect()
    const btn = trigger()
    fireEvent.click(btn)
    fireEvent.keyDown(btn, { key: "a" })
    expect(btn).toHaveAttribute("aria-activedescendant", optionId(0))
  })

  it("does not retain type-ahead input received while closed", () => {
    renderSelect()
    const btn = trigger()
    fireEvent.keyDown(btn, { key: "a" })
    fireEvent.click(btn)
    fireEvent.keyDown(btn, { key: "c" })
    expect(btn).toHaveAttribute("aria-activedescendant", optionId(2))
  })

  it("cancels the prior type-ahead reset when typing within the debounce window", () => {
    vi.useFakeTimers()
    try {
      renderSelect()
      const btn = trigger()
      fireEvent.click(btn)
      fireEvent.keyDown(btn, { key: "b" })
      vi.advanceTimersByTime(400)
      fireEvent.keyDown(btn, { key: "a" })
      vi.advanceTimersByTime(100)
      fireEvent.keyDown(btn, { key: "c" })
      expect(btn).toHaveAttribute("aria-activedescendant", optionId(1))
    } finally {
      vi.useRealTimers()
    }
  })

  it("ignores type-ahead characters while the listbox is closed", () => {
    renderSelect()
    const btn = trigger()
    fireEvent.keyDown(btn, { key: "b" })

    expect(btn).toHaveAttribute("aria-expanded", "false")
    expect(btn).not.toHaveAttribute("aria-activedescendant")
  })

  it("type-ahead with no match leaves the active option unchanged", () => {
    renderSelect()
    const btn = trigger()
    fireEvent.click(btn) // active 0
    fireEvent.keyDown(btn, { key: "z" })
    expect(btn).toHaveAttribute("aria-activedescendant", optionId(0))
  })

  it("ignores modified and multi-character type-ahead keys", () => {
    const specialOptions = [
      { value: "arrow", label: "Arrow" },
      { value: "beta", label: "Beta" },
    ]
    render(<Select id="special" options={specialOptions} value="beta" />)
    const btn = trigger()
    fireEvent.click(btn)
    expect(btn).toHaveAttribute("aria-activedescendant", "special-option-1")
    fireEvent.keyDown(btn, { key: "Arrow" })
    fireEvent.keyDown(btn, { key: "b", ctrlKey: true })
    fireEvent.keyDown(btn, { key: "b", metaKey: true })
    expect(btn).toHaveAttribute("aria-activedescendant", "special-option-1")
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

  it("keeps closed-only navigation keys and modified type-ahead inert", () => {
    renderSelect()
    const btn = trigger()

    for (const key of ["Home", "End", "Escape", "Tab"]) {
      fireEvent.keyDown(btn, { key })
    }
    fireEvent.keyDown(btn, { key: "b", ctrlKey: true })

    expect(btn).toHaveAttribute("aria-expanded", "false")
    expect(btn).not.toHaveAttribute("aria-activedescendant")
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

describe("Select — empty options", () => {
  it("keeps an empty listbox without an active descendant during navigation", () => {
    const getElementById = vi.spyOn(document, "getElementById")
    render(<Select id="empty" options={[]} />)
    const btn = screen.getByRole("combobox")

    fireEvent.click(btn)
    expect(btn).not.toHaveAttribute("aria-activedescendant")
    expect(getElementById).not.toHaveBeenCalled()

    fireEvent.keyDown(btn, { key: "ArrowDown" })
    fireEvent.keyDown(btn, { key: "ArrowUp" })
    expect(btn).not.toHaveAttribute("aria-activedescendant")
    expect(getElementById).not.toHaveBeenCalled()
  })

  it("ignores selection when no option exists at the active index", () => {
    const onValueChange = vi.fn()
    render(<Select id="empty" options={[]} onValueChange={onValueChange} />)
    const btn = screen.getByRole("combobox")

    fireEvent.click(btn)
    fireEvent.keyDown(btn, { key: "Enter" })

    expect(onValueChange).not.toHaveBeenCalled()
    expect(btn).not.toHaveAttribute("aria-activedescendant")
    expect(btn).toHaveAttribute("aria-expanded", "false")
  })

  it("does not notify when selection resolves to no option", () => {
    const onValueChange = vi.fn()
    render(<Select id="empty" options={[]} onValueChange={onValueChange} />)
    const btn = screen.getByRole("combobox")
    fireEvent.click(btn)
    fireEvent.keyDown(btn, { key: "Enter" })
    expect(onValueChange).not.toHaveBeenCalled()
  })

  it("initializes a missing active index when options arrive while open", () => {
    const firstView = render(<Select id="empty-down" options={[]} />)
    const firstButton = screen.getByRole("combobox")
    fireEvent.click(firstButton)
    firstView.rerender(<Select id="empty-down" options={OPTIONS} />)
    fireEvent.keyDown(firstButton, { key: "ArrowDown" })
    expect(firstButton).toHaveAttribute("aria-activedescendant", "empty-down-option-0")

    const secondView = render(<Select id="empty-up" options={[]} />)
    const secondButton = screen.getAllByRole("combobox").at(-1)!
    fireEvent.click(secondButton)
    secondView.rerender(<Select id="empty-up" options={OPTIONS} />)
    fireEvent.keyDown(secondButton, { key: "ArrowUp" })
    expect(secondButton).toHaveAttribute("aria-activedescendant", "empty-up-option-0")
  })
})
