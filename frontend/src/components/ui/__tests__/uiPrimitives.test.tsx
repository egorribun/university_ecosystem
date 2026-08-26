import { LazyMotion, domAnimation } from "framer-motion"
import { createRef } from "react"
import { describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"

import { Badge } from "@/components/ui/Badge"
import { Checkbox } from "@/components/ui/Checkbox"
import { EmptyState } from "@/components/ui/EmptyState"
import { ProgressBar } from "@/components/ui/ProgressBar"
import { Switch } from "@/components/ui/Switch"
import { Tooltip } from "@/components/ui/Tooltip"

// framer-motion `m.*` components require a LazyMotion ancestor with features.
const renderMotion = (ui: React.ReactElement) =>
  render(<LazyMotion features={domAnimation}>{ui}</LazyMotion>)

// --------------------------------------------------------------------------- #
// Badge — label/children, icons, polymorphic `as`, variant/tone combos        #
// --------------------------------------------------------------------------- #

describe("Badge", () => {
  it("renders label text and the default span element", () => {
    const { container } = render(<Badge label="New" />)
    expect(screen.getByText("New")).toBeInTheDocument()
    expect(container.querySelector("span")).toBeInTheDocument()
  })

  it("prefers children over label", () => {
    render(
      <Badge label="ignored">
        <span data-testid="child">kid</span>
      </Badge>
    )
    expect(screen.getByTestId("child")).toHaveTextContent("kid")
    expect(screen.queryByText("ignored")).not.toBeInTheDocument()
  })

  it("renders leading and trailing icons", () => {
    render(
      <Badge
        label="x"
        leadingIcon={<i data-testid="lead" />}
        trailingIcon={<i data-testid="trail" />}
      />
    )
    expect(screen.getByTestId("lead")).toBeInTheDocument()
    expect(screen.getByTestId("trail")).toBeInTheDocument()
  })

  it("renders as a custom element with outline + primary variants", () => {
    // `as` selects the rendered element; the polymorphic generic pins extra
    // DOM props to the default ("span"), so href is intentionally omitted here
    // (the W163 "as-prop is type-unreachable" gotcha) — the branch under test is
    // the `as ?? "span"` element selection, not attribute forwarding.
    render(
      <Badge as="a" variant="outline" tone="primary" shape="circle" size="md">
        link
      </Badge>
    )
    expect(screen.getByText("link").closest("a")).toBeInTheDocument()
  })
})

// --------------------------------------------------------------------------- #
// EmptyState — heading level, optional icon/description/action                 #
// --------------------------------------------------------------------------- #

describe("EmptyState", () => {
  it("renders the title as an h2 by default", () => {
    render(<EmptyState title="Nothing here" />)
    const heading = screen.getByRole("heading", { name: "Nothing here" })
    expect(heading.tagName).toBe("H2")
  })

  it("honours titleAs and renders icon/description/action when provided", () => {
    render(
      <EmptyState
        title="Empty"
        titleAs="h3"
        description="No items yet"
        icon={<i data-testid="icon" />}
        action={<button>Add</button>}
      />
    )
    expect(screen.getByRole("heading", { name: "Empty" }).tagName).toBe("H3")
    expect(screen.getByText("No items yet")).toBeInTheDocument()
    expect(screen.getByTestId("icon")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Add" })).toBeInTheDocument()
  })
})

// --------------------------------------------------------------------------- #
// ProgressBar — value clamping, indeterminate, max<=0 fallback, liveRegion     #
// --------------------------------------------------------------------------- #

describe("ProgressBar", () => {
  it("reports a clamped value and 50% width", () => {
    render(<ProgressBar value={50} max={100} ariaLabel="loading" />)
    const bar = screen.getByRole("progressbar")
    expect(bar).toHaveAttribute("aria-valuenow", "50")
    expect(bar).toHaveAttribute("aria-valuemax", "100")
    expect(bar).toHaveAttribute("aria-label", "loading")
    expect(bar.firstElementChild).toHaveStyle({ width: "50%" })
  })

  it("treats a null value as indeterminate (no aria-valuenow)", () => {
    render(<ProgressBar value={null} />)
    expect(screen.getByRole("progressbar")).not.toHaveAttribute("aria-valuenow")
  })

  it("clamps over-max and negative values into range", () => {
    const { rerender } = render(<ProgressBar value={150} max={100} />)
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100")
    rerender(<ProgressBar value={-10} max={100} />)
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0")
  })

  it("falls back to a safe max when max<=0 and sets aria-live when requested", () => {
    render(<ProgressBar value={10} max={0} liveRegion animated={false} />)
    const bar = screen.getByRole("progressbar")
    expect(bar).toHaveAttribute("aria-valuemax", "100")
    expect(bar).toHaveAttribute("aria-live", "polite")
  })
})

// --------------------------------------------------------------------------- #
// Tooltip — string content (title attr) vs node content (sr-only region)       #
// --------------------------------------------------------------------------- #

describe("Tooltip", () => {
  it("renders the element referenced by aria-describedby for string content", () => {
    render(
      <Tooltip content="Help text">
        <button>act</button>
      </Tooltip>
    )
    const btn = screen.getByRole("button", { name: "act" })
    expect(btn).toHaveAttribute("title", "Help text")
    expect(btn).toHaveAttribute("data-tooltip", "Help text")
    const tooltip = screen.getByRole("tooltip")
    expect(btn).toHaveAttribute("aria-describedby", tooltip.id)
    expect(tooltip).toHaveTextContent("Help text")
  })

  it("renders an sr-only tooltip region for node content (no title attr)", () => {
    render(
      <Tooltip content={<strong>rich</strong>}>
        <button>act</button>
      </Tooltip>
    )
    expect(screen.getByRole("tooltip")).toHaveTextContent("rich")
    expect(screen.getByRole("button", { name: "act" })).not.toHaveAttribute("title")
  })
})

// --------------------------------------------------------------------------- #
// Checkbox — checked/indeterminate icons + onCheckedChange                     #
// --------------------------------------------------------------------------- #

describe("Checkbox", () => {
  it("provides a 44px target and exposes the native indeterminate state", () => {
    const { container } = renderMotion(<Checkbox checked="indeterminate" />)
    const checkbox = screen.getByRole("checkbox") as HTMLInputElement
    expect(checkbox.closest("label")).toHaveClass("min-h-11", "min-w-11")
    expect(checkbox.indeterminate).toBe(true)
    expect(checkbox).toHaveAttribute("aria-checked", "mixed")
    expect(container.querySelector(".lucide-minus")).toBeInTheDocument()
  })

  it("shows the check glyph when checked and fires onCheckedChange on click", () => {
    const onChange = vi.fn()
    const { container } = renderMotion(<Checkbox checked={false} onCheckedChange={onChange} />)
    expect(container.querySelector(".lucide-check")).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("checkbox"))
    expect(onChange).toHaveBeenCalledWith(true)
  })

  it("renders the minus glyph for the indeterminate state", () => {
    const { container } = renderMotion(<Checkbox checked="indeterminate" />)
    expect(container.querySelector(".lucide-minus")).toBeInTheDocument()
  })

  it("renders a check glyph when checked", () => {
    const { container } = renderMotion(<Checkbox checked />)
    expect(container.querySelector(".lucide-check")).toBeInTheDocument()
  })

  it("forwards the native input ref and renders the disabled contract", () => {
    const ref = createRef<HTMLInputElement>()
    const { container } = renderMotion(<Checkbox ref={ref} disabled className="custom-checkbox" />)

    expect(ref.current).toBe(screen.getByRole("checkbox"))
    expect(ref.current).toBeDisabled()
    expect(container.querySelector(".custom-checkbox")).toHaveStyle({
      opacity: "var(--opacity-medium)",
    })
    fireEvent.click(ref.current!)
  })
})

// --------------------------------------------------------------------------- #
// Switch — change/focus/blur handlers + disabled                              #
// --------------------------------------------------------------------------- #

describe("Switch", () => {
  it("fires onCheckedChange and tracks focus/blur", () => {
    const onChange = vi.fn()
    renderMotion(<Switch checked={false} onCheckedChange={onChange} />)
    const input = screen.getByRole("switch")

    fireEvent.focus(input)
    fireEvent.click(input)
    fireEvent.blur(input)

    expect(onChange).toHaveBeenCalledWith(true)
    expect(input.closest("span")).toHaveClass("min-h-11")
  })

  it("renders disabled without crashing", () => {
    renderMotion(<Switch checked disabled />)
    expect(screen.getByRole("switch")).toBeDisabled()
  })
})
