import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"

const logger = vi.hoisted(() => ({
  logError: vi.fn(),
  logWarning: vi.fn(),
  logInfo: vi.fn(),
}))

const haptics = vi.hoisted(() => ({
  trigger: vi.fn(),
}))

const motionState = vi.hoisted(() => ({
  calls: [] as Array<{ element: string; props: Record<string, unknown> }>,
}))

vi.mock("@/app/logger", () => logger)

vi.mock("@/hooks/useHaptics", () => ({
  useHaptics: () => ({ trigger: haptics.trigger }),
}))

vi.mock("framer-motion", async () => {
  const { framerMotionMock } = await import("@/tests/helpers/framerMotionMock")
  const base = framerMotionMock() as {
    m: Record<string, unknown>
    motion: Record<string, unknown>
    [key: string]: unknown
  }

  const wrapMotion = (motion: Record<string, unknown>) =>
    new Proxy(motion, {
      get(target, property, receiver) {
        const component = Reflect.get(target, property, receiver)
        if (typeof component !== "function") return component
        return (props: Record<string, unknown>) => {
          motionState.calls.push({ element: String(property), props })
          return (component as (nextProps: Record<string, unknown>) => ReactNode)(props)
        }
      },
    })

  const wrappedMotion = wrapMotion(base.m)
  return { ...base, m: wrappedMotion, motion: wrappedMotion }
})

import {
  initGlobalErrorHandlers,
  resetGlobalErrorHandlersForTesting,
} from "@/app/globalErrorHandlers"
import { ContentCard } from "@/components/ui/ContentCard"
import { Checkbox } from "@/components/ui/Checkbox"
import { ConfirmDialog } from "@/components/ui/ConfirmDialog"
import { Dialog } from "@/components/ui/Dialog"
import { GlobalHapticsListener } from "@/components/ui/GlobalHapticsListener"
import { MediaSlot } from "@/components/ui/MediaSlot"
import { NotificationRelevanceScore } from "@/components/ui/NotificationRelevanceScore"
import NewsCardSkeleton, {
  NewsCardSkeleton as NamedNewsCardSkeleton,
} from "@/components/ui/NewsCardSkeleton"
import { ProfileCardSkeleton } from "@/components/ui/ProfileCardSkeleton"
import { RadioGroup, RadioGroupItem } from "@/components/ui/RadioGroup"
import { DataTablePagination } from "@/components/ui/data-table/DataTablePagination"
import type { DataTableInstance } from "@/components/ui/data-table/dataTableFeatures"
import { FadeIn } from "@/components/ui/motion/FadeIn"
import { ScaleIn } from "@/components/ui/motion/ScaleIn"
import { motion as motionTokens } from "@/theme/tokens"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

type Listener = (event: unknown) => void

function latestMotionProps(element: string): Record<string, unknown> {
  const call = [...motionState.calls].reverse().find((entry) => entry.element === element)
  expect(call).toBeDefined()
  return call?.props ?? {}
}

function makeTable({
  canPrevious = true,
  canNext = true,
}: { canPrevious?: boolean; canNext?: boolean } = {}): DataTableInstance<Record<string, never>> {
  return {
    getFilteredSelectedRowModel: () => ({ rows: [{}] }),
    getFilteredRowModel: () => ({ rows: [{}, {}, {}, {}] }),
    state: { pagination: { pageIndex: 1, pageSize: 20 } },
    getPageCount: () => 3,
    getCanPreviousPage: () => canPrevious,
    getCanNextPage: () => canNext,
    setPageSize: vi.fn(),
    setPageIndex: vi.fn(),
    previousPage: vi.fn(),
    nextPage: vi.fn(),
  } as unknown as DataTableInstance<Record<string, never>>
}

afterEach(() => {
  cleanup()
  resetGlobalErrorHandlersForTesting()
  motionState.calls.length = 0
  haptics.trigger = vi.fn()
  document.body.style.overflow = ""
  vi.restoreAllMocks()
  vi.unstubAllEnvs()
})

describe("Checkbox survivor contract", () => {
  it("keeps native state, indeterminate state, visual states, and optional callbacks observable", () => {
    const onCheckedChange = vi.fn()
    const { rerender } = render(
      <Checkbox
        aria-label="Select record"
        checked={false}
        className="custom-checkbox"
        onCheckedChange={onCheckedChange}
      />
    )
    const input = screen.getByRole("checkbox", { name: "Select record" })
    const visual = input.parentElement?.querySelector("div")
    expect(input).not.toBeChecked()
    expect(visual).toHaveClass(
      "flex",
      "h-6",
      "w-6",
      "border-glass-border",
      "bg-glass-bg",
      "backdrop-blur-glass",
      "shadow-glass",
      "hover:border-brand/(--opacity-medium)",
      "hover:bg-glass-tint1",
      "peer-focus-visible:ring-4",
      "peer-focus-visible:ring-brand/(--opacity-dim)",
      "custom-checkbox"
    )

    fireEvent.click(input)
    expect(onCheckedChange).toHaveBeenCalledWith(true)

    rerender(<Checkbox aria-label="Select record" checked="indeterminate" />)
    expect(input).not.toBeChecked()
    expect(input).toHaveAttribute("aria-checked", "mixed")
    expect(input).toHaveProperty("indeterminate", true)
    expect(input.parentElement?.querySelector("div")).toHaveClass(
      "border-brand",
      "bg-brand/(--opacity-dim)",
      "shadow-glow-primary"
    )
    expect(input.parentElement?.querySelector("svg path")).toHaveAttribute("d", "M5 12h14")
    expect(input.parentElement?.querySelector("svg")).toHaveStyle({ strokeWidth: "3" })

    rerender(<Checkbox aria-label="Select record" checked disabled />)
    expect(input).toBeChecked()
    expect(input).toBeDisabled()
    expect(input.parentElement?.querySelector("div")).toHaveClass("cursor-not-allowed", "grayscale")
    expect(input.parentElement?.querySelector("div")).toHaveStyle({
      opacity: "var(--opacity-medium)",
    })
    expect(input.parentElement?.querySelector("svg path")).toHaveAttribute("d", "M20 6 9 17l-5-5")
    expect(input.parentElement?.querySelector("svg")).toHaveStyle({ strokeWidth: "4" })
    expect(Checkbox.displayName).toBe("Checkbox")
    expect(latestMotionProps("div")).toMatchObject({
      initial: { scale: 0.5, opacity: 0 },
      animate: { scale: 1, opacity: 1 },
      exit: { scale: 0.5, opacity: 0 },
      transition: { type: "spring", stiffness: 500, damping: 30 },
      className: "text-brand check-celebrate",
    })
  })

  it("does not require a callback for native changes", () => {
    render(<Checkbox aria-label="No callback" />)
    const input = screen.getByRole("checkbox", { name: "No callback" })
    // Invoke React's bound handler directly instead of dispatching a browser
    // event.  React intentionally rethrows event-handler failures through the
    // global error channel, which would make the OptionalChaining mutant look
    // like a Stryker runtime error instead of a killed mutant.  Calling the
    // exact handler synchronously keeps the optional-callback contract
    // observable while allowing the assertion to capture the mutant throw.
    const reactPropsKey = Object.keys(input).find((key) => key.startsWith("__reactProps$"))
    expect(reactPropsKey).toBeDefined()
    type ChangeHandler = (event: { target: HTMLInputElement }) => void
    const onChange = (input as unknown as Record<string, { onChange?: ChangeHandler } | undefined>)[
      reactPropsKey ?? ""
    ]?.onChange
    expect(onChange).toBeTypeOf("function")
    expect(() => onChange?.({ target: input as HTMLInputElement })).not.toThrow()
  })
})

describe("GlobalHapticsListener lifecycle contract", () => {
  it("fails closed for clicks outside a haptic target", () => {
    const errorEvents: ErrorEvent[] = []
    const onError = (event: ErrorEvent) => {
      event.preventDefault()
      errorEvents.push(event)
    }
    window.addEventListener("error", onError)
    try {
      render(<GlobalHapticsListener />)
      fireEvent.click(document.body)
      expect(haptics.trigger).not.toHaveBeenCalled()
      expect(errorEvents).toHaveLength(0)
    } finally {
      window.removeEventListener("error", onError)
    }
  })

  it("guards the listener when invoked with a non-element event target", () => {
    const addEventListener = vi.spyOn(document, "addEventListener")
    render(<GlobalHapticsListener />)
    const registered = addEventListener.mock.calls.find(([type]) => type === "click")?.[1]
    expect(registered).toEqual(expect.any(Function))

    expect(() => (registered as EventListener)(new MouseEvent("click"))).not.toThrow()
    expect(haptics.trigger).not.toHaveBeenCalled()
  })

  it("removes the exact click listener on unmount", () => {
    const addEventListener = vi.spyOn(document, "addEventListener")
    const removeEventListener = vi.spyOn(document, "removeEventListener")
    const { unmount } = render(<GlobalHapticsListener />)

    const registered = addEventListener.mock.calls.find(([type]) => type === "click")?.[1]
    expect(registered).toEqual(expect.any(Function))

    unmount()
    expect(removeEventListener).toHaveBeenCalledWith("click", registered)
  })

  it("rebinds the listener when the haptic trigger identity changes", () => {
    const addEventListener = vi.spyOn(document, "addEventListener")
    const removeEventListener = vi.spyOn(document, "removeEventListener")
    const { rerender, unmount } = render(<GlobalHapticsListener />)

    const firstRegistered = addEventListener.mock.calls.find(([type]) => type === "click")?.[1]
    expect(firstRegistered).toEqual(expect.any(Function))

    haptics.trigger = vi.fn()
    rerender(<GlobalHapticsListener />)
    expect(removeEventListener).toHaveBeenCalledWith("click", firstRegistered)
    expect(addEventListener.mock.calls.filter(([type]) => type === "click")).toHaveLength(2)

    unmount()
  })
})

describe("ContentCard and RadioGroup survivor contracts", () => {
  it("applies non-default badge variants and preserves compound display names", () => {
    render(
      <ContentCard>
        <ContentCard.Badge variant="success">Success</ContentCard.Badge>
        <ContentCard.Badge variant="warning">Warning</ContentCard.Badge>
        <ContentCard.Badge variant="error">Error</ContentCard.Badge>
        <ContentCard.Badge variant="info">Info</ContentCard.Badge>
      </ContentCard>
    )

    expect(screen.getByText("Success")).toHaveClass("bg-success-bg", "text-success-text")
    expect(screen.getByText("Warning")).toHaveClass("bg-warning-bg", "text-warning-text")
    expect(screen.getByText("Error")).toHaveClass("bg-error-bg", "text-error-text")
    expect(screen.getByText("Info")).toHaveClass("bg-brand-subtle", "text-brand")
    expect(ContentCard.Badge.displayName).toBe("ContentCard.Badge")
  })

  it("propagates selection and disabled state through the radio group contract", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <RadioGroup value="one" name="choice" onChange={onChange} row aria-label="Choices">
        <RadioGroupItem value="one" aria-label="One" />
        <RadioGroupItem value="two" aria-label="Two" />
        <RadioGroupItem value="empty" aria-label="Empty" disabled />
      </RadioGroup>
    )

    const group = screen.getByRole("radiogroup", { name: "Choices" })
    expect(group).toHaveClass("flex", "flex-row", "flex-wrap", "gap-4")
    expect(RadioGroup.displayName).toBe("RadioGroup")
    expect(RadioGroupItem.displayName).toBe("RadioGroupItem")

    const one = screen.getByRole("radio", { name: "One" })
    const two = screen.getByRole("radio", { name: "Two" })
    const empty = screen.getByRole("radio", { name: "Empty" })
    expect(one).toBeChecked()
    expect(two).not.toBeChecked()
    expect(empty).toBeDisabled()

    await user.click(two)
    expect(onChange).toHaveBeenCalledWith(null, "two")
    expect(onChange).toHaveBeenCalledTimes(1)
  })
})

describe("MediaSlot survivor contract", () => {
  it("renders explicit and default fallbacks without creating an image", () => {
    const { container } = render(
      <MediaSlot
        aspectRatio="4/3"
        containerClassName="media-container"
        fallback={<span>Custom fallback</span>}
      />
    )
    const wrapper = screen.getByText("Custom fallback").parentElement
    expect(wrapper).toHaveClass(
      "relative",
      "w-full",
      "overflow-hidden",
      "bg-(--glass-bg)",
      "media-container"
    )
    expect(wrapper).toHaveStyle({ aspectRatio: "4/3" })
    expect(container.querySelector("img")).toBeNull()

    const { container: defaultContainer } = render(<MediaSlot />)
    const defaultWrapper = defaultContainer.firstElementChild
    expect(defaultWrapper).toHaveClass("relative", "w-full", "overflow-hidden")
    expect(defaultWrapper?.querySelector("svg")).toHaveClass(
      "h-12",
      "w-12",
      "text-text-primary/(--opacity-dim)"
    )
  })

  it("exposes loading, loaded, zoom, and error transitions with optional callbacks", () => {
    const onLoad = vi.fn()
    const onError = vi.fn()
    const { container } = render(
      <MediaSlot
        src="https://img.example/cover.jpg"
        alt="Cover"
        aspectRatio="1/1"
        className="image-class"
        containerClassName="container-class"
        fallback={<span>Error fallback</span>}
        loadingPlaceholder={<span>Loading placeholder</span>}
        onLoad={onLoad}
        onError={onError}
      />
    )

    const image = screen.getByRole("img", { name: "Cover" })
    expect(image).toHaveAttribute("src", "https://img.example/cover.jpg")
    expect(image).toHaveAttribute("loading", "lazy")
    expect(image).toHaveClass("opacity-0", "group-hover:scale-105", "image-class")
    expect(image.parentElement).toHaveClass(
      "relative",
      "w-full",
      "overflow-hidden",
      "bg-(--glass-bg)",
      "container-class"
    )
    expect(image.parentElement).toHaveStyle({ aspectRatio: "1/1" })
    expect(screen.getByText("Loading placeholder")).toBeInTheDocument()

    fireEvent.load(image)
    expect(onLoad).toHaveBeenCalledOnce()
    expect(screen.queryByText("Loading placeholder")).not.toBeInTheDocument()
    expect(image).toHaveClass("opacity-100")

    fireEvent.error(image)
    expect(onError).toHaveBeenCalledOnce()
    expect(screen.getByText("Error fallback")).toBeInTheDocument()
    expect(container.querySelector("img")).toBeNull()
  })

  it("does not require load/error callbacks and honors an explicit zoom opt-out", () => {
    const { container } = render(
      <MediaSlot src="https://img.example/no-zoom.jpg" hoverZoom={false} />
    )
    const image = screen.getByRole("img")
    expect(image).not.toHaveClass("group-hover:scale-105")
    expect(container.querySelector(".animate-spin")).not.toBeNull()
    expect(() => fireEvent.load(image)).not.toThrow()
    expect(() => fireEvent.error(image)).not.toThrow()
    expect(container.querySelector("img")).toBeNull()
    expect(container.querySelector("svg")).toHaveClass("h-10", "w-10", "text-(--text-tertiary)")
    expect(MediaSlot.displayName).toBe("MediaSlot")
  })
})

describe("NewsCardSkeleton survivor contract", () => {
  it("keeps compact geometry and all skeleton dimensions stable", () => {
    const { container } = render(<NewsCardSkeleton featured={false} />)
    const article = container.querySelector("article")
    expect(article).toHaveClass(
      "relative",
      "flex",
      "h-full",
      "w-full",
      "overflow-hidden",
      "rounded-2xl",
      "card-matte",
      "glass-noise",
      "flex-col"
    )
    expect(article).not.toHaveClass("lg:flex-row")
    expect(container.querySelector(".bg-input-mix")).toHaveClass("h-48", "sm:h-52")

    const content = container.querySelector(".bg-input-mix")?.nextElementSibling
    expect(content).toHaveClass("flex", "flex-1", "flex-col", "gap-4", "p-5")
    expect(content).not.toHaveClass("sm:p-6", "lg:p-8", "lg:justify-center")
    expect(container.querySelector(".bg-input-mix .skeleton")).toHaveClass("rounded-none")
    expect(
      Array.from(container.querySelectorAll<HTMLElement>("[aria-hidden='true']")).map(
        (skeleton) => [skeleton.style.width, skeleton.style.height]
      )
    ).toEqual([
      ["", ""],
      ["70%", "1.25rem"],
      ["100%", "0.875rem"],
      ["90%", "0.875rem"],
      ["3rem", "1rem"],
      ["3rem", "1rem"],
    ])
  })

  it("keeps featured geometry and the additional summary skeleton distinct", () => {
    const { container } = render(<NewsCardSkeleton featured />)
    const article = container.querySelector("article")
    expect(article).toHaveClass("lg:flex-row", "flex-col")
    const image = container.querySelector(".bg-input-mix")
    expect(image).toHaveClass("h-56", "sm:h-64", "lg:w-[55%]", "lg:h-auto", "lg:min-h-[20rem]")
    const content = image?.nextElementSibling
    expect(content).toHaveClass("sm:p-6", "lg:p-8", "lg:justify-center")
    expect(container.querySelector(".bg-input-mix .skeleton")).toHaveClass("rounded-none")
    expect(NamedNewsCardSkeleton.displayName).toBe("NewsCardSkeleton")
    expect(
      Array.from(container.querySelectorAll<HTMLElement>("[aria-hidden='true']")).map(
        (skeleton) => [skeleton.style.width, skeleton.style.height]
      )
    ).toEqual([
      ["", ""],
      ["85%", "1.5rem"],
      ["100%", "0.875rem"],
      ["90%", "0.875rem"],
      ["75%", "0.875rem"],
      ["3rem", "1rem"],
      ["3rem", "1rem"],
    ])
  })
})

describe("DataTablePagination survivor contract", () => {
  it("publishes every page-size option and labels the combobox", async () => {
    const user = userEvent.setup()
    const table = makeTable()
    render(<DataTablePagination table={table} />)

    const combobox = screen.getByRole("combobox")
    expect(combobox).toHaveAttribute("aria-labelledby", "data-table-pagination-pagesize-label")
    expect(combobox).toHaveTextContent("20")
    expect(document.getElementById("data-table-pagination-pagesize-label")).toHaveTextContent(/\S/u)
    expect(screen.getAllByRole("button").every((button) => button.textContent?.trim())).toBe(true)
    await user.click(combobox)
    expect(screen.getAllByRole("option").map((option) => option.textContent)).toEqual([
      "10",
      "20",
      "30",
      "40",
      "50",
    ])
    fireEvent.mouseDown(screen.getByRole("option", { name: "30" }))
    expect(table.setPageSize).toHaveBeenCalledWith(30)
  })

  it("disables boundary navigation and preserves the selected/page summary", () => {
    const table = makeTable({ canPrevious: false, canNext: false })
    render(<DataTablePagination table={table} />)
    expect(screen.getByText(/1 of 4 row\(s\) selected/)).toBeInTheDocument()
    expect(screen.getByText("Page 2 of 3")).toBeInTheDocument()

    const buttons = screen.getAllByRole("button")
    expect(buttons).toHaveLength(4)
    expect(buttons.every((button) => (button as HTMLButtonElement).disabled)).toBe(true)
    for (const button of buttons) fireEvent.click(button)
    expect(table.setPageIndex).not.toHaveBeenCalled()
    expect(table.previousPage).not.toHaveBeenCalled()
    expect(table.nextPage).not.toHaveBeenCalled()
  })
})

describe("motion survivor contract", () => {
  it("passes the complete ScaleIn variants and Lighthouse initial contract", () => {
    render(
      <ScaleIn className="scale-card" delay={0.25} duration={0.4} initialScale={0.8}>
        <span>Scaled content</span>
      </ScaleIn>
    )
    const normal = latestMotionProps("div")
    expect(normal).toMatchObject({
      initial: "hidden",
      animate: "visible",
      exit: "exit",
      className: "scale-card",
    })
    expect(normal.variants).toEqual({
      hidden: { opacity: 0, scale: 0.8 },
      visible: {
        opacity: 1,
        scale: 1,
        transition: { duration: 0.4, delay: 0.25, ease: [0.22, 1, 0.36, 1] },
      },
      exit: {
        opacity: 0,
        scale: 0.8,
        transition: { duration: motionTokens.durationFast },
      },
    })

    cleanup()
    motionState.calls.length = 0
    vi.stubEnv("VITE_LHCI", "true")
    render(<ScaleIn>Paintable content</ScaleIn>)
    expect(latestMotionProps("div")).toMatchObject({
      initial: false,
      animate: "visible",
      exit: "exit",
    })
  })

  it.each([
    ["up", { opacity: 0, y: 12 }],
    ["down", { opacity: 0, y: -12 }],
    ["left", { opacity: 0, x: 12 }],
    ["right", { opacity: 0, x: -12 }],
    ["none", { opacity: 0 }],
  ] as const)("passes the %s FadeIn direction and timing contract", (direction, initial) => {
    render(
      <FadeIn direction={direction} distance={12} delay={0.1} duration={0.3}>
        {direction}
      </FadeIn>
    )
    const props = latestMotionProps("div")
    expect(props).toMatchObject({ initial: "hidden", animate: "visible", exit: "exit" })
    expect(props.variants).toEqual({
      hidden: initial,
      visible: {
        opacity: 1,
        y: 0,
        x: 0,
        transition: { duration: 0.3, delay: 0.1, ease: [0.22, 1, 0.36, 1] },
      },
      exit: { opacity: 0, transition: { duration: motionTokens.durationFast } },
    })
  })
})

describe("global error handler survivor contract", () => {
  beforeEach(() => {
    logger.logError.mockClear()
    logger.logWarning.mockClear()
    logger.logInfo.mockClear()
  })

  it("does not serialize a null rejection reason", () => {
    const listeners: Record<string, Listener[]> = {}
    const target = {
      addEventListener: (type: string, listener: Listener) => {
        listeners[type] = [...(listeners[type] ?? []), listener]
      },
      removeEventListener: () => undefined,
    } as unknown as Parameters<typeof initGlobalErrorHandlers>[0]
    initGlobalErrorHandlers(target)

    const stringify = vi.spyOn(JSON, "stringify")
    listeners.unhandledrejection?.[0]?.({ reason: null } as PromiseRejectionEvent)
    expect(stringify).not.toHaveBeenCalled()
    expect(logger.logWarning).toHaveBeenCalledWith(
      "[GlobalErrors] Promise rejected with a non-error value",
      null
    )
  })
})

describe("Dialog survivor contract", () => {
  it("gates portal content, wires ARIA, locks body scroll, and restores trigger focus", async () => {
    document.body.style.overflow = "scroll"
    const user = userEvent.setup()
    const onClose = vi.fn()
    const view = render(
      <>
        <button type="button">Open dialog</button>
        <Dialog open={false} onClose={onClose} title="Record details" subtitle="Read-only">
          <p>Dialog content</p>
        </Dialog>
      </>
    )

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    const trigger = screen.getByRole("button", { name: "Open dialog" })
    trigger.focus()

    view.rerender(
      <>
        <button type="button">Open dialog</button>
        <Dialog open onClose={onClose} title="Record details" subtitle="Read-only">
          <p>Dialog content</p>
        </Dialog>
      </>
    )

    const dialog = await screen.findByRole("dialog", { name: "Record details" })
    expect(dialog).toHaveAttribute("aria-modal", "true")
    const labelledBy = dialog.getAttribute("aria-labelledby")
    const describedBy = dialog.getAttribute("aria-describedby")
    expect(labelledBy).toBeTruthy()
    expect(describedBy).toBeTruthy()
    expect(document.getElementById(labelledBy!)).toHaveTextContent("Record details")
    expect(document.getElementById(describedBy!)).toHaveTextContent("Read-only")
    expect(screen.getByText("Dialog content")).toBeInTheDocument()
    expect(document.body.style.overflow).toBe("hidden")
    await waitFor(() => expect(dialog).toContainElement(document.activeElement as HTMLElement))

    await user.click(screen.getByRole("button", { name: "Close" }))
    expect(onClose).toHaveBeenCalledOnce()

    view.rerender(
      <>
        <button type="button">Open dialog</button>
        <Dialog open={false} onClose={onClose} title="Record details" subtitle="Read-only">
          <p>Dialog content</p>
        </Dialog>
      </>
    )
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
    expect(document.body.style.overflow).toBe("scroll")
    await waitFor(() => expect(screen.getByRole("button", { name: "Open dialog" })).toHaveFocus())
  })

  it("preserves explicit accessible names and size/mobile/footer geometry", async () => {
    render(
      <Dialog
        open
        onClose={vi.fn()}
        ariaLabel="Keyboard shortcuts"
        size="lg"
        fullScreenOnMobile
        className="dialog-custom"
        bodyClassName="body-custom"
        footerClassName="footer-custom"
        footer={<button type="button">Apply</button>}
      >
        <p>Shortcut list</p>
      </Dialog>
    )

    const dialog = await screen.findByRole("dialog", { name: "Keyboard shortcuts" })
    expect(dialog).not.toHaveAttribute("aria-labelledby")
    expect(dialog).toHaveClass(
      "sm:max-w-[42rem]",
      "h-dvh",
      "max-h-dvh",
      "rounded-none",
      "dialog-custom"
    )
    expect(dialog.querySelector(".body-custom")).toHaveTextContent("Shortcut list")
    expect(dialog.querySelector(".footer-custom")).toContainElement(
      screen.getByRole("button", { name: "Apply" })
    )
    expect(screen.getByRole("button", { name: "Close" })).toHaveClass("h-11", "w-11")
  })

  it("honors initialFocus=false without moving focus to dialog content", async () => {
    render(
      <Dialog open onClose={vi.fn()} title="Focus policy" initialFocus={false}>
        <button type="button">Dialog target</button>
      </Dialog>
    )

    const dialog = await screen.findByRole("dialog", { name: "Focus policy" })
    expect(dialog).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Dialog target" })).not.toHaveFocus()
  })
})

describe("ConfirmDialog survivor contract", () => {
  const makeProps = () => ({
    open: true,
    title: "Delete item?",
    message: "This cannot be undone.",
    confirmText: "Delete",
    cancelText: "Cancel",
    onConfirm: vi.fn(),
    onCancel: vi.fn(),
  })

  it("renders an alertdialog with fully linked title and message", () => {
    render(<ConfirmDialog {...makeProps()} />)
    const dialog = screen.getByRole("alertdialog")
    expect(dialog).toHaveAttribute("aria-modal", "true")
    const labelledBy = dialog.getAttribute("aria-labelledby")
    const describedBy = dialog.getAttribute("aria-describedby")
    expect(labelledBy).toBeTruthy()
    expect(describedBy).toBeTruthy()
    expect(document.getElementById(labelledBy!)).toHaveTextContent("Delete item?")
    expect(document.getElementById(describedBy!)).toHaveTextContent("This cannot be undone.")
    expect(dialog.parentElement).toHaveAttribute("role", "presentation")
  })

  it.each([
    ["default", "bg-primary-main"],
    ["warning", "bg-warning-text"],
    ["danger", "bg-error-text"],
  ] as const)("keeps the %s confirm color contract", (variant, colorClass) => {
    render(<ConfirmDialog {...makeProps()} variant={variant} />)
    const confirm = screen.getByRole("button", { name: "Delete" })
    expect(confirm).toHaveClass(colorClass, "px-6", "py-3", "focus-ring-premium")
    expect(confirm).not.toHaveClass(
      ...(["bg-primary-main", "bg-warning-text", "bg-error-text"].filter(
        (candidate) => candidate !== colorClass
      ) as [string, ...string[]])
    )
  })

  it("disables both actions and exposes the loading state without losing labels", async () => {
    const props = makeProps()
    const user = userEvent.setup()
    const view = render(<ConfirmDialog {...props} isLoading />)
    const cancel = screen.getByRole("button", { name: "Cancel" })
    const confirm = screen.getByRole("button", { name: "Delete" })
    expect(cancel).toBeDisabled()
    expect(confirm).toBeDisabled()
    expect(confirm).toHaveAttribute("aria-busy", "true")
    expect(confirm.querySelector(".animate-spin")).toBeInTheDocument()

    await user.click(cancel)
    await user.click(confirm)
    expect(props.onCancel).not.toHaveBeenCalled()
    expect(props.onConfirm).not.toHaveBeenCalled()

    view.rerender(<ConfirmDialog {...props} isLoading={false} />)
    expect(screen.getByRole("button", { name: "Cancel" })).not.toBeDisabled()
    expect(screen.getByRole("button", { name: "Delete" })).not.toBeDisabled()
    expect(screen.getByRole("button", { name: "Delete" })).not.toHaveAttribute("aria-busy", "true")
  })

  it("dispatches the correct action and gates the closed state", async () => {
    const props = makeProps()
    const user = userEvent.setup()
    const view = render(<ConfirmDialog {...props} open={false} />)
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument()

    view.rerender(<ConfirmDialog {...props} open />)
    await user.click(screen.getByRole("button", { name: "Cancel" }))
    await user.click(screen.getByRole("button", { name: "Delete" }))
    expect(props.onCancel).toHaveBeenCalledOnce()
    expect(props.onConfirm).toHaveBeenCalledOnce()
  })
})

describe("NotificationRelevanceScore survivor contract", () => {
  it.each([
    ["high", "High relevance", "bg-brand", [true, false, false]],
    ["medium", "Medium relevance", "bg-warning-text", [true, true, false]],
    ["low", "Low relevance", "bg-(--text-tertiary)", [true, true, true]],
  ] as const)(
    "renders translated labels and exact dot progression for %s",
    async (relevance, label, activeColor, activeDots) => {
      window.localStorage.setItem("ue:language", "en")
      const { container } = await renderWithRouter({
        ui: () => <NotificationRelevanceScore relevance={relevance} />,
        authProvider: false,
      })

      const indicator = await screen.findByLabelText(label)
      expect(indicator).toHaveAttribute("title", label)
      expect(indicator).toHaveClass("flex", "items-center", "gap-1")
      expect(container.querySelectorAll('[aria-hidden="true"]')).toHaveLength(3)
      const dots = Array.from(indicator.querySelectorAll<HTMLElement>('span[aria-hidden="true"]'))
      expect(dots).toHaveLength(3)
      expect(dots.map((dot) => dot.classList.contains(activeColor))).toEqual(activeDots)
      expect(
        dots.map((dot) => dot.classList.contains("bg-(--text-tertiary)/(--opacity-faint)"))
      ).toEqual(activeDots.map((active) => !active))
    }
  )

  it("forwards custom styling without changing the accessible translation", async () => {
    window.localStorage.setItem("ue:language", "en")
    const { container } = await renderWithRouter({
      ui: () => <NotificationRelevanceScore relevance="high" className="relevance-custom" />,
      authProvider: false,
    })
    const indicator = await screen.findByLabelText("High relevance")
    expect(container.querySelector("div.relevance-custom")).toBe(indicator)
    expect(indicator).toHaveAttribute("aria-label", "High relevance")
  })
})

describe("ProfileCardSkeleton survivor contract", () => {
  it("keeps translated loading semantics and predictable cover/content geometry", async () => {
    window.localStorage.setItem("ue:language", "en")
    await renderWithRouter({
      ui: () => <ProfileCardSkeleton className="profile-skeleton-custom" />,
      authProvider: false,
    })
    const card = await screen.findByLabelText("Loading profile")
    expect(card).toHaveAttribute("aria-busy", "true")
    expect(card).toHaveClass(
      "rounded-2xl",
      "border",
      "bg-input-mix",
      "overflow-hidden",
      "profile-skeleton-custom"
    )
    expect(card.querySelector(".animate-skeleton-wave")).toHaveClass("h-32", "sm:h-40", "lg:h-48")
    expect(await screen.findByRole("status", { name: "Loading avatar" })).toHaveStyle({
      width: "80px",
      height: "80px",
    })
    expect(await screen.findByRole("status", { name: "Loading name" })).toHaveStyle({
      width: "180px",
      height: "24px",
    })
    expect(card.querySelectorAll('[role="status"]')).toHaveLength(2)
    expect(card.querySelectorAll('.skeleton[aria-hidden="true"]')).toHaveLength(9)
    expect(card.querySelectorAll(".flex.flex-col.items-center")).toHaveLength(3)
  })

  it("omits the cover while retaining avatar overlap fallback geometry", async () => {
    window.localStorage.setItem("ue:language", "en")
    await renderWithRouter({
      ui: () => <ProfileCardSkeleton showCover={false} />,
      authProvider: false,
    })
    const card = await screen.findByLabelText("Loading profile")
    const content = card.querySelector(".relative")
    const avatarOffset = content?.querySelector(".mb-4")
    expect(card.querySelector(".animate-skeleton-wave")).toBeNull()
    expect(avatarOffset).toHaveClass("mt-4")
    expect(avatarOffset).not.toHaveClass("-mt-12")
    expect(await screen.findByRole("status", { name: "Loading avatar" })).toBeInTheDocument()
    expect(card.querySelectorAll(".flex.flex-col.items-center")).toHaveLength(3)
  })
})
