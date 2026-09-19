import { cleanup, fireEvent, render, renderHook, screen, act } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"

const motionValueFactory = () => {
  let value = 0
  return {
    get: () => value,
    set: (next: number) => {
      value = next
    },
    on: () => () => undefined,
    destroy: () => undefined,
    clearListeners: () => undefined,
    toString: () => String(value),
  }
}

vi.mock("framer-motion", () => ({
  m: {
    span: ({
      animate,
      initial,
      transition,
      ...props
    }: {
      animate?: unknown
      initial?: unknown
      transition?: unknown
      [key: string]: unknown
    }) => (
      <span
        {...props}
        data-animate={JSON.stringify(animate)}
        data-initial={JSON.stringify(initial)}
        data-transition={JSON.stringify(transition)}
      />
    ),
    div: (props: Record<string, unknown>) => {
      const { children, style, ...rest } = props
      return (
        <div {...rest} style={style as React.CSSProperties}>
          {children as ReactNode}
        </div>
      )
    },
  },
  useMotionValue: () => motionValueFactory(),
  MotionValue: class MotionValue {},
}))

vi.mock("@/hooks/useFocusTrap", () => ({
  default: () => ({ current: null }),
}))

import { Card } from "@/components/ui/Card"
import { Dialog } from "@/components/ui/Dialog"
import { GlassCard } from "@/components/ui/GlassCard"
import { Input } from "@/components/ui/Input"
import { LiveRegionProvider, useAnnouncer } from "@/components/ui/LiveRegionProvider"
import { MediaSlot } from "@/components/ui/MediaSlot"
import { ProgressBar } from "@/components/ui/ProgressBar"
import { SkeletonMorph } from "@/components/ui/SkeletonMorph"
import { Spotlight, SpotlightOverlay, useSpotlight } from "@/components/ui/Spotlight"
import { Switch } from "@/components/ui/Switch"

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

function AnnouncerProbe() {
  const { announce } = useAnnouncer()
  return (
    <div>
      <button type="button" onClick={() => announce("polite message", "polite")}>
        polite
      </button>
      <button type="button" onClick={() => announce("assertive message", "assertive")}>
        assertive
      </button>
    </div>
  )
}

describe("LiveRegionProvider survivor contracts", () => {
  it("starts with two empty, correctly labelled live regions", () => {
    render(
      <LiveRegionProvider>
        <AnnouncerProbe />
      </LiveRegionProvider>
    )

    const status = screen.getByRole("status")
    const alert = screen.getByRole("alert")
    expect(status).toHaveAttribute("aria-live", "polite")
    expect(status).toHaveAttribute("aria-atomic", "true")
    expect(status).toHaveClass("sr-only")
    expect(status).toHaveTextContent("")
    expect(alert).toHaveAttribute("aria-live", "assertive")
    expect(alert).toHaveAttribute("aria-atomic", "true")
    expect(alert).toHaveClass("sr-only")
    expect(alert).toHaveTextContent("")
  })

  it("keeps channels independent and clears only the replaced timeout", () => {
    vi.useFakeTimers()
    render(
      <LiveRegionProvider>
        <AnnouncerProbe />
      </LiveRegionProvider>
    )

    fireEvent.click(screen.getByRole("button", { name: "polite" }))
    act(() => vi.advanceTimersByTime(2_500))
    fireEvent.click(screen.getByRole("button", { name: "assertive" }))
    act(() => vi.advanceTimersByTime(400))
    expect(screen.getByRole("status")).toHaveTextContent("polite message")
    expect(screen.getByRole("alert")).toHaveTextContent("assertive message")

    fireEvent.click(screen.getByRole("button", { name: "polite" }))
    act(() => vi.advanceTimersByTime(200))
    expect(screen.getByRole("status")).toHaveTextContent("polite message")
    act(() => vi.advanceTimersByTime(2_800))
    expect(screen.getByRole("status")).toHaveTextContent("")
    expect(screen.getByRole("alert")).toHaveTextContent("")
  })
})

describe("SkeletonMorph survivor contracts", () => {
  it("keeps loaded and loading geometry, semantics, and children distinct", () => {
    const { container, rerender } = render(
      <SkeletonMorph
        loaded={false}
        className="custom-morph"
        skeleton={<span>Loading placeholder</span>}
      >
        <span>Loaded content</span>
      </SkeletonMorph>
    )

    const root = container.firstElementChild as HTMLElement
    const skeleton = root.querySelector(".skeleton-morph-skeleton") as HTMLElement
    const content = root.querySelector(".skeleton-morph-content") as HTMLElement
    expect(root).toHaveClass("skeleton-morph-container", "relative", "custom-morph")
    expect(skeleton).toHaveAttribute("data-loaded", "false")
    expect(skeleton).toHaveAttribute("aria-hidden", "false")
    expect(skeleton).not.toHaveClass("absolute", "inset-0", "overflow-hidden")
    expect(content).toHaveAttribute("data-loaded", "false")
    expect(content).toHaveClass("skeleton-morph-content", "absolute", "inset-0")
    expect(content).not.toHaveTextContent("Loaded content")

    rerender(
      <SkeletonMorph loaded skeleton={<span>Loading placeholder</span>}>
        <span>Loaded content</span>
      </SkeletonMorph>
    )
    const loadedSkeleton = container.querySelector(".skeleton-morph-skeleton") as HTMLElement
    const loadedContent = container.querySelector(".skeleton-morph-content") as HTMLElement
    expect(loadedSkeleton).toHaveClass(
      "skeleton-morph-skeleton",
      "absolute",
      "inset-0",
      "overflow-hidden"
    )
    expect(loadedSkeleton).toHaveAttribute("data-loaded", "true")
    expect(loadedSkeleton).toHaveAttribute("aria-hidden", "true")
    expect(loadedContent).toHaveClass("skeleton-morph-content")
    expect(loadedContent).not.toHaveClass("absolute", "inset-0")
    expect(loadedContent).toHaveAttribute("data-loaded", "true")
    expect(loadedContent).toHaveTextContent("Loaded content")
  })
})

describe("Input survivor contracts", () => {
  it("preserves the base, default, error, width, and size variants", () => {
    const { rerender } = render(<Input aria-label="Default input" />)
    const input = screen.getByRole("textbox", { name: "Default input" })
    expect(input).toHaveClass(
      "flex",
      "min-h-12",
      "w-full",
      "rounded-lg",
      "border",
      "border-border-subtle",
      "bg-surface",
      "px-4",
      "py-3",
      "text-base",
      "font-medium",
      "text-text-primary",
      "shadow-sm",
      "transition-all",
      "duration-slow",
      "placeholder:text-text-tertiary",
      "focus:border-border-focus",
      "input-focus-glow",
      "disabled:cursor-not-allowed",
      "disabled:opacity-medium",
      "file:border-0",
      "file:bg-transparent",
      "file:text-sm",
      "file:font-medium"
    )
    expect(input).toHaveAttribute("aria-invalid", "false")

    rerender(
      <Input aria-label="Error input" error fullWidth={false} size="lg" className="custom-input" />
    )
    expect(screen.getByRole("textbox", { name: "Error input" })).toHaveClass(
      "custom-input",
      "border-error-text",
      "focus:border-error-text",
      "focus:ring-error-text/(--opacity-subtle)",
      "w-auto",
      "px-5",
      "py-4",
      "text-lg",
      "min-h-14"
    )
    expect(screen.getByRole("textbox", { name: "Error input" })).toHaveAttribute(
      "aria-invalid",
      "true"
    )

    rerender(<Input aria-label="Small input" size="sm" />)
    expect(screen.getByRole("textbox", { name: "Small input" })).toHaveClass(
      "px-3",
      "py-2",
      "text-sm",
      "min-h-11"
    )
    expect(Input.displayName).toBe("Input")
  })
})

describe("Switch survivor contracts", () => {
  it("keeps motion transitions, visual states, and the diagnostic name stable", () => {
    const { container, rerender } = render(<Switch checked={false} aria-label="Toggle" />)
    const input = screen.getByRole("switch", { name: "Toggle" })
    const root = input.parentElement as HTMLElement
    const [, track, thumb] = Array.from(root.children) as HTMLElement[]
    expect(JSON.parse(track?.dataset.transition ?? "null")).toEqual({ duration: 0.2 })
    expect(JSON.parse(thumb?.dataset.transition ?? "null")).toEqual({
      type: "spring",
      stiffness: 500,
      damping: 30,
    })
    expect(track).toHaveClass(
      "absolute",
      "inset-x-0",
      "top-2",
      "h-7",
      "rounded-full",
      "border",
      "border-border-subtle",
      "transition-colors",
      "duration-base",
      "bg-(--bg-surface)-tint",
      "backdrop-blur-sm"
    )
    expect(thumb).toHaveClass(
      "relative",
      "z-deep",
      "ml-0.5",
      "block",
      "h-5.5",
      "w-5.5",
      "rounded-full",
      "bg-surface",
      "shadow-surface",
      "border",
      "border-glass-border-subtle"
    )

    fireEvent.mouseEnter(root)
    expect(JSON.parse(thumb?.dataset.animate ?? "null")).toMatchObject({ scale: 1.1 })
    rerender(<Switch checked disabled aria-label="Toggle" />)
    expect(root).toHaveClass("cursor-not-allowed", "opacity-medium")
    expect(JSON.parse(thumb?.dataset.animate ?? "null")).toMatchObject({ x: 28 })
    expect(Switch.displayName).toBe("Switch")
    expect(container.firstElementChild).toBe(root)
  })
})

describe("Card and GlassCard survivor contracts", () => {
  it("keeps default and explicit Card hover states distinct", () => {
    const { container, rerender } = render(<Card>Card body</Card>)
    const card = container.firstElementChild as HTMLElement
    expect(card).toHaveClass(
      "relative",
      "flex",
      "flex-col",
      "rounded-xl",
      "border",
      "border-border-subtle",
      "bg-(--bg-surface)",
      "text-text-primary",
      "shadow-surface",
      "transition-premium",
      "p-4"
    )
    expect(card).not.toHaveClass("hover:-translate-y-1.5", "focus-ring-premium")

    rerender(
      <Card hoverable padding="none">
        Card body
      </Card>
    )
    expect(container.firstElementChild).toHaveClass(
      "p-0",
      "hover:-translate-y-1.5",
      "hover:scale-hover-lift",
      "hover:shadow-premium-lift",
      "focus-ring-premium",
      "motion-reduce:hover:translate-y-0",
      "motion-reduce:hover:scale-100",
      "motion-reduce:transition-shadow"
    )
    expect(Card.displayName).toBe("Card")
  })

  it("keeps GlassCard defaults, variants, sheen, and interactive state observable", () => {
    const { container, rerender } = render(<GlassCard>Glass body</GlassCard>)
    const card = container.firstElementChild as HTMLElement
    expect(card).toHaveClass(
      "glass-noise",
      "relative",
      "overflow-hidden",
      "rounded-xl",
      "border",
      "border-glass-border",
      "shadow-glass",
      "transition-all",
      "duration-premium",
      "bg-glass",
      "backdrop-blur-xl"
    )
    expect(card).not.toHaveClass("card-hover-lift", "cursor-pointer", "Stryker")
    expect(card.querySelector(".pointer-events-none")).toHaveClass(
      "absolute",
      "inset-0",
      "bg-linear-to-br",
      "from-white/(--opacity-subtle)",
      "via-transparent",
      "to-transparent",
      "opacity-medium"
    )

    rerender(
      <GlassCard intensity="low" radius="3xl" interactive>
        Glass body
      </GlassCard>
    )
    expect(container.firstElementChild).toHaveClass(
      "bg-(--glass-bg-low)",
      "dark:bg-(--glass-bg-low-dark)",
      "backdrop-blur-md",
      "rounded-3xl",
      "card-hover-lift",
      "hover:bg-glass-tint1",
      "cursor-pointer"
    )
  })
})

describe("ProgressBar, MediaSlot, Dialog, Spotlight survivor contracts", () => {
  it("keeps the numeric type guard fail-closed", () => {
    const isFinite = vi.spyOn(Number, "isFinite").mockReturnValue(true)
    render(<ProgressBar value={"50" as unknown as number} ariaLabel="Progress" />)
    const progress = screen.getByRole("progressbar", { name: "Progress" })
    expect(progress).not.toHaveAttribute("aria-valuenow")
    expect(progress.firstElementChild).toHaveStyle({ width: "0%" })
    expect(isFinite).not.toHaveBeenCalled()
  })

  it("calls MediaSlot load and error callbacks exactly once", () => {
    const onLoad = vi.fn()
    const onError = vi.fn()
    const { container } = render(
      <MediaSlot
        src="https://img.example/survivor.jpg"
        alt="Survivor"
        onLoad={onLoad}
        onError={onError}
      />
    )
    const image = screen.getByRole("img", { name: "Survivor" })
    fireEvent.load(image)
    expect(onLoad).toHaveBeenCalledOnce()
    fireEvent.error(image)
    expect(onError).toHaveBeenCalledOnce()
    expect(container.querySelector("img")).toBeNull()
  })

  it("publishes the Spotlight overlay geometry and follows fresh motion values", () => {
    const { result, rerender } = renderHook(() => useSpotlight())
    const firstX = result.current.mouseX
    rerender()
    const secondX = result.current.mouseX
    expect(secondX).not.toBe(firstX)

    act(() => {
      result.current.onMouseMove({
        currentTarget: { getBoundingClientRect: () => ({ left: 10, top: 20 }) },
        clientX: 45,
        clientY: 65,
      } as never)
    })
    expect(secondX.get()).toBe(35)
    expect(firstX.get()).toBe(0)

    const { container } = render(
      <SpotlightOverlay mouseX={secondX} mouseY={result.current.mouseY} />
    )
    const overlay = container.firstElementChild as HTMLElement
    expect(overlay.style.borderRadius).toBe("inherit")
    expect(overlay.style.background).toContain("radial-gradient")
    expect(overlay.style.background).toContain("35px")

    const spotlight = render(
      <Spotlight className="custom-spotlight">
        <span>child</span>
      </Spotlight>
    )
    expect(spotlight.container.firstElementChild).toHaveClass(
      "group",
      "relative",
      "overflow-hidden",
      "custom-spotlight"
    )
  })

  it("removes a Dialog portal when its owner unmounts", async () => {
    const view = render(
      <Dialog open onClose={vi.fn()} title="Cleanup dialog">
        body
      </Dialog>
    )
    expect(await screen.findByRole("dialog", { name: "Cleanup dialog" })).toBeInTheDocument()
    expect(document.querySelectorAll('[data-dialog-root="true"]')).toHaveLength(1)
    view.unmount()
    expect(document.querySelectorAll('[data-dialog-root="true"]')).toHaveLength(0)
  })
})
