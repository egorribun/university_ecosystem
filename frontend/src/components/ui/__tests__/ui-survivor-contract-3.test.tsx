import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { Input } from "@/components/ui/Input"
import { TextField } from "@/components/ui/TextField"
import { StoryCircle } from "@/components/ui/StoryCircle"
import Snackbar from "@/components/ui/Snackbar"
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { SEO } from "@/components/ui/SEO"
import { normalizeNewsListLimit } from "@/api/hooks/news"

const allClasses = (element: Element) => element.getAttribute("class") ?? ""

describe("small UI primitive mutation contracts", () => {
  it("keeps every Input variant default and visual contract", () => {
    const { rerender } = render(<Input aria-label="base" />)
    const input = screen.getByRole("textbox", { name: "base" })
    expect(allClasses(input)).toContain("flex")
    expect(allClasses(input)).toContain("min-h-12")
    expect(allClasses(input)).toContain("w-full")
    expect(allClasses(input)).toContain("rounded-lg")
    expect(allClasses(input)).toContain("border-border-subtle")
    expect(allClasses(input)).toContain("bg-surface")
    expect(allClasses(input)).toContain("px-4")
    expect(allClasses(input)).toContain("py-3")
    expect(allClasses(input)).toContain("text-base")
    expect(allClasses(input)).toContain("font-medium")
    expect(allClasses(input)).toContain("text-text-primary")
    expect(allClasses(input)).toContain("shadow-sm")
    expect(allClasses(input)).toContain("disabled:cursor-not-allowed")
    expect(allClasses(input)).toContain("file:font-medium")
    expect(input).toHaveAttribute("aria-invalid", "false")

    rerender(<Input aria-label="error" error fullWidth={false} size="sm" />)
    const errorInput = screen.getByRole("textbox", { name: "error" })
    expect(allClasses(errorInput)).toContain("border-error-text")
    expect(allClasses(errorInput)).toContain("focus:ring-error-text/(--opacity-subtle)")
    expect(allClasses(errorInput)).toContain("w-auto")
    expect(allClasses(errorInput)).toContain("px-3")
    expect(allClasses(errorInput)).toContain("py-2")
    expect(allClasses(errorInput)).toContain("text-sm")
    expect(allClasses(errorInput)).toContain("min-h-11")
    expect(errorInput).toHaveAttribute("aria-invalid", "true")

    rerender(<Input aria-label="large" size="lg" className="caller-class" />)
    const largeInput = screen.getByRole("textbox", { name: "large" })
    expect(allClasses(largeInput)).toContain("px-5")
    expect(allClasses(largeInput)).toContain("py-4")
    expect(allClasses(largeInput)).toContain("text-lg")
    expect(allClasses(largeInput)).toContain("min-h-14")
    expect(largeInput).toHaveClass("caller-class")
  })

  it("keeps TextField icon, width, multiline, and feedback contracts", () => {
    const onChange = vi.fn()
    const onBlur = vi.fn()
    const { rerender, container } = render(
      <TextField
        id="field"
        label="Label"
        value="value"
        onChange={onChange}
        onBlur={onBlur}
        fullWidth
        leadingIcon={<span data-testid="leading">L</span>}
        trailingIcon={<span data-testid="trailing">T</span>}
        helperText="Helpful"
      />
    )
    const input = screen.getByLabelText("Label")
    expect(input).toHaveAttribute("id", "field")
    expect(input).toHaveAttribute("type", "text")
    expect(allClasses(container.firstElementChild!)).toContain("flex")
    expect(allClasses(container.firstElementChild!)).toContain("gap-1.5")
    expect(allClasses(container.firstElementChild!)).toContain("w-full")
    expect(allClasses(input)).toContain("pl-11")
    expect(allClasses(input)).toContain("pr-11")
    expect(screen.getByTestId("leading")).toBeInTheDocument()
    expect(screen.getByTestId("trailing")).toBeInTheDocument()
    expect(screen.getByText("Helpful")).toHaveClass(
      "px-1",
      "text-xs",
      "font-medium",
      "leading-tight",
      "text-(--text-tertiary)/(--opacity-strong)"
    )
    fireEvent.change(input, { target: { value: "next" } })
    fireEvent.blur(input)
    expect(onChange).toHaveBeenCalledOnce()
    expect(onBlur).toHaveBeenCalledOnce()

    rerender(
      <TextField
        value="notes"
        onChange={onChange}
        multiline
        rows={4}
        error
        helperText="Invalid"
        fullWidth={false}
        inputClassName="custom-input"
      />
    )
    const area = screen.getByRole("textbox")
    expect(area.tagName).toBe("TEXTAREA")
    expect(area).toHaveAttribute("rows", "4")
    expect(area).toHaveAttribute("aria-invalid", "true")
    expect(area).toHaveAttribute("aria-describedby")
    expect(area).toHaveClass("resize-none", "custom-input")
    expect(screen.getByRole("alert")).toHaveClass("text-(--error-text)")
    expect(container.firstElementChild).not.toHaveClass("w-full")
  })

  it("keeps StoryCircle size, border conversion, and focus affordances", () => {
    const { rerender } = render(
      <StoryCircle as="button" size="sm" borderWidth={4} aria-label="story">
        avatar
      </StoryCircle>
    )
    const button = screen.getByRole("button", { name: "story" })
    expect(button).toHaveClass(
      "group/story",
      "relative",
      "inline-flex",
      "items-center",
      "justify-center",
      "overflow-visible",
      "rounded-full",
      "text-white",
      "bg-linear-to-br",
      "shadow-lg",
      "transition-opacity",
      "duration-base",
      "ease-premium",
      "hover:opacity-80",
      "focus-visible:outline-(--primary-main)",
      "focus-visible:ring-1"
    )
    expect(button).toHaveClass(
      "h-(--size-story-sm)",
      "w-(--size-story-sm)",
      "min-h-(--size-story-sm)",
      "min-w-(--size-story-sm)"
    )
    expect(button.style.borderWidth).toBe("0.25rem")
    const focusRing = button.querySelector("span[aria-hidden]")!
    expect(focusRing).toHaveClass(
      "pointer-events-none",
      "absolute",
      "inset-0",
      "rounded-full",
      "border",
      "opacity-0",
      "group-hover/story:opacity-medium"
    )
    expect(button.querySelector("span.relative")).toHaveClass(
      "relative",
      "z-deep",
      "flex",
      "h-full",
      "w-full",
      "items-center",
      "justify-center",
      "overflow-hidden",
      "rounded-full"
    )

    rerender(
      <StoryCircle size="lg" borderWidth="thin" className="custom">
        content
      </StoryCircle>
    )
    const circle = screen.getByText("content").closest("div")!
    expect(circle).toHaveClass("h-(--size-story-lg)", "w-(--size-story-lg)", "custom")
    expect(circle.style.borderWidth).toBe("thin")
  })

  it("keeps Snackbar visibility and timer cleanup semantics", () => {
    vi.useFakeTimers()
    const onClose = vi.fn()
    const { rerender, container } = render(
      <Snackbar open message="Saved" onClose={onClose} duration={500} />
    )
    expect(screen.getByRole("status")).toHaveTextContent("Saved")
    vi.advanceTimersByTime(499)
    expect(onClose).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(onClose).toHaveBeenCalledOnce()
    rerender(<Snackbar open message="" onClose={onClose} />)
    expect(container.firstChild).toBeNull()
    rerender(<Snackbar open={false} message="Hidden" onClose={onClose} />)
    expect(container.firstChild).toBeNull()
    vi.useRealTimers()
  })
})

describe("table primitive mutation contracts", () => {
  it("preserves semantic elements, classes, and ref forwarding", () => {
    render(
      <Table className="table-custom" data-testid="table">
        <TableCaption className="caption-custom">Caption</TableCaption>
        <TableHeader className="head-custom">
          <TableRow className="row-custom">
            <TableHead className="th-custom">Name</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody className="body-custom">
          <TableRow data-state="selected">
            <TableCell className="cell-custom">Ada</TableCell>
          </TableRow>
        </TableBody>
        <TableFooter className="footer-custom">
          <TableRow>
            <TableCell>Total</TableCell>
          </TableRow>
        </TableFooter>
      </Table>
    )
    const table = screen.getByRole("table")
    expect(table).toHaveClass("w-full", "caption-bottom", "text-sm", "table-custom")
    expect(table.parentElement).toHaveClass("relative", "w-full", "overflow-auto")
    expect(screen.getByText("Caption")).toHaveClass(
      "mt-4",
      "text-sm",
      "text-text-tertiary",
      "caption-custom"
    )
    expect(screen.getByRole("columnheader")).toHaveClass(
      "h-10",
      "px-2",
      "text-left",
      "align-middle",
      "font-medium",
      "text-text-secondary",
      "th-custom"
    )
    expect(screen.getByText("Ada")).toHaveClass("p-2", "align-middle", "cell-custom")
    expect(screen.getByText("Name").closest("tr")).toHaveClass(
      "border-b",
      "transition-colors",
      "hover:bg-surface-hover/50",
      "data-[state=selected]:bg-surface-selected",
      "row-custom"
    )
    expect(screen.getByText("Ada").closest("tr")).toHaveClass(
      "border-b",
      "transition-colors",
      "hover:bg-surface-hover/50",
      "data-[state=selected]:bg-surface-selected"
    )
    expect(table.querySelector("thead")).toHaveClass("[&_tr]:border-b", "head-custom")
    expect(table.querySelector("tbody")).toHaveClass("[&_tr:last-child]:border-0", "body-custom")
    expect(table.querySelector("tfoot")).toHaveClass(
      "border-t",
      "bg-surface/50",
      "font-medium",
      "[&>tr]:last:border-b-0",
      "footer-custom"
    )
  })
})

describe("SEO and news boundary contracts", () => {
  it("renders complete metadata when optional values exist and omits it otherwise", () => {
    const { rerender } = render(
      <SEO
        title="Article"
        description="Description"
        image="https://example.test/cover.png"
        type="article"
      />
    )
    expect(document.title).toBe("Article | University Ecosystem")
    expect(document.querySelector('meta[name="title"]')).toHaveAttribute(
      "content",
      "Article | University Ecosystem"
    )
    expect(document.querySelector('meta[name="description"]')).toHaveAttribute(
      "content",
      "Description"
    )
    expect(document.querySelector('meta[property="og:type"]')).toHaveAttribute("content", "article")
    expect(document.querySelector('meta[property="og:title"]')).toHaveAttribute(
      "content",
      "Article | University Ecosystem"
    )
    expect(document.querySelector('meta[property="og:description"]')).toHaveAttribute(
      "content",
      "Description"
    )
    expect(document.querySelector('meta[property="og:image"]')).toHaveAttribute(
      "content",
      "https://example.test/cover.png"
    )
    expect(document.querySelector('meta[name="twitter:card"]')).toHaveAttribute(
      "content",
      "summary_large_image"
    )
    expect(document.querySelector('meta[name="twitter:title"]')).toHaveAttribute(
      "content",
      "Article | University Ecosystem"
    )
    expect(document.querySelector('meta[name="twitter:description"]')).toHaveAttribute(
      "content",
      "Description"
    )
    expect(document.querySelector('meta[name="twitter:image"]')).toHaveAttribute(
      "content",
      "https://example.test/cover.png"
    )

    rerender(<SEO title="Home" />)
    expect(document.title).toBe("Home | University Ecosystem")
    expect(document.querySelector('meta[name="description"]')).not.toBeInTheDocument()
    expect(document.querySelector('meta[property="og:description"]')).not.toBeInTheDocument()
    expect(document.querySelector('meta[property="og:image"]')).not.toBeInTheDocument()
    expect(document.querySelector('meta[name="twitter:description"]')).not.toBeInTheDocument()
    expect(document.querySelector('meta[name="twitter:image"]')).not.toBeInTheDocument()
    expect(document.querySelector('meta[property="og:type"]')).toHaveAttribute("content", "website")
  })

  it.each([
    [undefined, 12],
    [Number.NaN, 12],
    [0, 12],
    [-2, 12],
    [1.9, 1],
    [25, 25],
  ] as const)("normalizes news limit %s to %s", (value, expected) => {
    expect(normalizeNewsListLimit(value)).toBe(expected)
  })
})
