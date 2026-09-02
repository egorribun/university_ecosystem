import { LazyMotion, domAnimation } from "framer-motion"
import { describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"

import { Button } from "@/components/ui/Button"
import { Card } from "@/components/ui/Card"
import { Input } from "@/components/ui/Input"
import { RadioGroup, RadioGroupItem } from "@/components/ui/RadioGroup"
import { Select } from "@/components/ui/Select"
import { TextField } from "@/components/ui/TextField"
import { Textarea } from "@/components/ui/Textarea"

// Select calls useTranslation("common"); the other six components below don't
// use i18n, so a file-level stub is the simplest self-contained provider.
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}))

// framer-motion `m.*` (RadioGroupItem indicator, Select listbox) need LazyMotion.
const renderMotion = (ui: React.ReactElement) =>
  render(<LazyMotion features={domAnimation}>{ui}</LazyMotion>)

// --------------------------------------------------------------------------- #
// Button — loading/disabled gating, polymorphic `as`, haptics, icons          #
// --------------------------------------------------------------------------- #

describe("Button", () => {
  it("keeps compact and icon controls at least 44px tall and wide", () => {
    const { rerender } = render(<Button size="sm">Compact</Button>)
    expect(screen.getByRole("button", { name: "Compact" })).toHaveClass("min-h-11")

    rerender(
      <Button size="icon" aria-label="Icon action">
        <span aria-hidden>+</span>
      </Button>
    )
    expect(screen.getByRole("button", { name: "Icon action" })).toHaveClass(
      "h-11",
      "w-11",
      "min-h-11",
      "min-w-11"
    )
  })

  it("renders an enabled solid button and fires onClick", () => {
    const onClick = vi.fn()
    render(<Button onClick={onClick}>Click</Button>)
    const btn = screen.getByRole("button", { name: "Click" })
    expect(btn).not.toBeDisabled()
    fireEvent.click(btn)
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it("shows aria-busy + disables and blocks onClick while loading", () => {
    const onClick = vi.fn()
    render(
      <Button loading onClick={onClick} leadingIcon={<i data-testid="lead" />}>
        Save
      </Button>
    )
    const btn = screen.getByRole("button")
    expect(btn).toHaveAttribute("aria-busy", "true")
    expect(btn).toBeDisabled()
    expect(screen.getByTestId("lead")).toBeInTheDocument()
    fireEvent.click(btn)
    expect(onClick).not.toHaveBeenCalled() // isDisabled → handleClick returns early
  })

  it("renders polymorphic as=a with aria-disabled and no disabled attr", () => {
    const onClick = vi.fn()
    render(
      <Button
        as="a"
        variant="outline"
        size="lg"
        disabled
        onClick={onClick}
        trailingIcon={<i data-testid="tr" />}
      >
        link
      </Button>
    )
    const link = screen.getByText("link").closest("a")
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute("aria-disabled", "true")
    expect(link).not.toHaveAttribute("disabled") // not a <button> element
    expect(screen.getByTestId("tr")).toBeInTheDocument()
    fireEvent.click(link!)
    expect(onClick).not.toHaveBeenCalled()
  })

  it("maps haptics: string passthrough, true→light, false→omitted", () => {
    const { rerender } = render(<Button haptics="heavy">a</Button>)
    expect(screen.getByRole("button")).toHaveAttribute("data-haptic", "heavy")
    rerender(<Button haptics>b</Button>)
    expect(screen.getByRole("button")).toHaveAttribute("data-haptic", "light")
    rerender(<Button haptics={false}>c</Button>)
    expect(screen.getByRole("button")).not.toHaveAttribute("data-haptic")
  })
})

// --------------------------------------------------------------------------- #
// Input / Textarea — aria-invalid from `error`, value forwarding              #
// --------------------------------------------------------------------------- #

describe("Input", () => {
  it("keeps the compact input at least 44px tall", () => {
    render(<Input size="sm" aria-label="Compact input" />)
    expect(screen.getByRole("textbox", { name: "Compact input" })).toHaveClass("min-h-11")
  })

  it("sets aria-invalid from error and forwards onChange", () => {
    const onChange = vi.fn()
    render(<Input value="x" onChange={onChange} error size="sm" placeholder="ph" />)
    const input = screen.getByPlaceholderText("ph")
    expect(input).toHaveAttribute("aria-invalid", "true")
    fireEvent.change(input, { target: { value: "y" } })
    expect(onChange).toHaveBeenCalled()
  })

  it("defaults aria-invalid to false", () => {
    render(<Input placeholder="p2" />)
    expect(screen.getByPlaceholderText("p2")).toHaveAttribute("aria-invalid", "false")
  })
})

describe("Textarea", () => {
  it("sets aria-invalid + rows and honors fullWidth=false", () => {
    render(<Textarea error fullWidth={false} rows={5} placeholder="t" />)
    const area = screen.getByPlaceholderText("t")
    expect(area).toHaveAttribute("aria-invalid", "true")
    expect(area).toHaveAttribute("rows", "5")
  })
})

// --------------------------------------------------------------------------- #
// Card — default div vs polymorphic element + variants                         #
// --------------------------------------------------------------------------- #

describe("Card", () => {
  it("renders a div with children by default", () => {
    render(<Card>body</Card>)
    expect(screen.getByText("body")).toBeInTheDocument()
  })

  it("renders polymorphic as=section with padding + hoverable", () => {
    const { container } = render(
      <Card as="section" padding="lg" hoverable>
        x
      </Card>
    )
    expect(container.querySelector("section")).toBeInTheDocument()
    expect(screen.getByText("x")).toBeInTheDocument()
  })
})

// --------------------------------------------------------------------------- #
// TextField — label, helper/error (aria-describedby + role=alert), multiline   #
// --------------------------------------------------------------------------- #

describe("TextField", () => {
  it("generates a control id when a labelled field does not receive one", () => {
    render(<TextField label="Generated label" value="" onChange={() => {}} />)
    const input = screen.getByLabelText("Generated label")
    expect(input.id).not.toBe("")
  })

  it("renders label + non-error helper wired via aria-describedby", () => {
    const onChange = vi.fn()
    render(<TextField id="f1" label="Name" value="v" onChange={onChange} helperText="hint" />)
    expect(screen.getByText("Name")).toBeInTheDocument()
    const input = screen.getByDisplayValue("v")
    expect(input).toHaveAttribute("aria-describedby")
    fireEvent.change(input, { target: { value: "v2" } })
    expect(onChange).toHaveBeenCalled()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument() // non-error
  })

  it("gives the error helper role=alert and the input aria-invalid", () => {
    render(<TextField value="" onChange={() => {}} error helperText="bad" />)
    expect(screen.getByRole("alert")).toHaveTextContent("bad")
    expect(screen.getByRole("textbox")).toHaveAttribute("aria-invalid", "true")
  })

  it("renders a textarea + icons in multiline mode", () => {
    const onChange = vi.fn()
    render(
      <TextField
        value="m"
        onChange={onChange}
        multiline
        rows={3}
        leadingIcon={<i data-testid="lead" />}
        trailingIcon={<i data-testid="tr" />}
      />
    )
    const area = screen.getByRole("textbox")
    expect(area.tagName).toBe("TEXTAREA")
    fireEvent.change(area, { target: { value: "m2" } })
    expect(onChange).toHaveBeenCalled()
    expect(screen.getByTestId("lead")).toBeInTheDocument()
    expect(screen.getByTestId("tr")).toBeInTheDocument()
    fireEvent.blur(area)
    expect(area).not.toHaveAttribute("aria-describedby")
  })

  it("wires multiline helper text and an optional blur handler", () => {
    const onBlur = vi.fn()
    render(
      <TextField
        value="notes"
        onChange={() => {}}
        onBlur={onBlur}
        multiline
        helperText="Formatting is supported"
      />
    )

    const area = screen.getByRole("textbox")
    expect(area).toHaveAttribute("aria-describedby")
    fireEvent.blur(area)
    expect(onBlur).toHaveBeenCalledOnce()
  })
})

// --------------------------------------------------------------------------- #
// RadioGroup — selection, onChange, disabled, context guard                    #
// --------------------------------------------------------------------------- #

describe("RadioGroup", () => {
  it("exposes a named radiogroup and 44px item targets", () => {
    renderMotion(
      <RadioGroup value="a" aria-label="Delivery method">
        <RadioGroupItem value="a" />
      </RadioGroup>
    )

    expect(screen.getByRole("radiogroup", { name: "Delivery method" })).toBeInTheDocument()
    expect(screen.getByRole("radio").nextElementSibling).toHaveClass("min-h-11", "min-w-11")
  })

  it("marks the selected item and fires onChange(null, value) on click", () => {
    const onChange = vi.fn()
    renderMotion(
      <RadioGroup value="b" onChange={onChange} name="g" row>
        <RadioGroupItem value="a" />
        <RadioGroupItem value="b" />
      </RadioGroup>
    )
    const radios = screen.getAllByRole("radio")
    expect(radios).toHaveLength(2)
    expect(radios[1]!).toBeChecked()
    fireEvent.click(radios[0]!)
    expect(onChange).toHaveBeenCalledWith(null, "a")
  })

  it("disables items when the group is disabled", () => {
    renderMotion(
      <RadioGroup value="a" disabled>
        <RadioGroupItem value="a" />
      </RadioGroup>
    )
    expect(screen.getByRole("radio")).toBeDisabled()
  })

  it("throws when RadioGroupItem is used outside a RadioGroup", () => {
    expect(() => render(<RadioGroupItem value="x" />)).toThrow(/within a RadioGroup/)
  })
})

// --------------------------------------------------------------------------- #
// Select — combobox open/close, mouse + keyboard selection, disabled no-op     #
// --------------------------------------------------------------------------- #

const SELECT_OPTIONS = [
  { value: "a", label: "Apple" },
  { value: "b", label: "Banana" },
  { value: "c", label: "Cherry" },
]

describe("Select", () => {
  it("shows the placeholder, opens on click, and selects via mouseDown", () => {
    const onValueChange = vi.fn()
    renderMotion(
      <Select
        options={SELECT_OPTIONS}
        onValueChange={onValueChange}
        placeholder="Pick"
        aria-label="fruit"
      />
    )
    const trigger = screen.getByRole("combobox", { name: "fruit" })
    expect(trigger).toHaveTextContent("Pick")
    expect(trigger).toHaveAttribute("aria-expanded", "false")

    fireEvent.click(trigger)
    expect(trigger).toHaveAttribute("aria-expanded", "true")

    fireEvent.mouseDown(screen.getByRole("option", { name: "Banana" }))
    expect(onValueChange).toHaveBeenCalledWith("b")
    expect(trigger).toHaveAttribute("aria-expanded", "false") // closed after select
  })

  it("renders the selected option's label", () => {
    renderMotion(<Select options={SELECT_OPTIONS} value="c" aria-label="f" />)
    expect(screen.getByRole("combobox")).toHaveTextContent("Cherry")
  })

  it("keyboard: ArrowDown opens, ArrowDown moves, Enter selects", () => {
    const onValueChange = vi.fn()
    renderMotion(<Select options={SELECT_OPTIONS} onValueChange={onValueChange} aria-label="f" />)
    const trigger = screen.getByRole("combobox")
    fireEvent.keyDown(trigger, { key: "ArrowDown" }) // open (activeIndex 0)
    expect(trigger).toHaveAttribute("aria-expanded", "true")
    fireEvent.keyDown(trigger, { key: "ArrowDown" }) // → index 1
    fireEvent.keyDown(trigger, { key: "Enter" }) // select active
    expect(onValueChange).toHaveBeenCalledTimes(1)
  })

  it("keyboard: Home/End/ArrowUp/type-ahead navigate, Escape closes", () => {
    renderMotion(<Select options={SELECT_OPTIONS} aria-label="f" />)
    const trigger = screen.getByRole("combobox")
    fireEvent.keyDown(trigger, { key: "ArrowDown" }) // open
    fireEvent.keyDown(trigger, { key: "End" })
    fireEvent.keyDown(trigger, { key: "ArrowUp" })
    fireEvent.keyDown(trigger, { key: "Home" })
    fireEvent.keyDown(trigger, { key: "c" }) // type-ahead → Cherry
    fireEvent.keyDown(trigger, { key: "Escape" })
    expect(trigger).toHaveAttribute("aria-expanded", "false")
  })

  it("is a no-op when disabled", () => {
    renderMotion(<Select options={SELECT_OPTIONS} disabled aria-label="f" />)
    const trigger = screen.getByRole("combobox")
    expect(trigger).toBeDisabled()
    fireEvent.keyDown(trigger, { key: "ArrowDown" }) // disabled → returns
    expect(trigger).toHaveAttribute("aria-expanded", "false")
  })
})
