import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"

const logger = vi.hoisted(() => ({
  logError: vi.fn(),
  logWarning: vi.fn(),
  logInfo: vi.fn(),
}))

const motionState = vi.hoisted(() => ({
  calls: [] as Array<{ element: string; props: Record<string, unknown> }>,
}))

vi.mock("@/app/logger", () => logger)

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
import { MediaSlot } from "@/components/ui/MediaSlot"
import NewsCardSkeleton, {
  NewsCardSkeleton as NamedNewsCardSkeleton,
} from "@/components/ui/NewsCardSkeleton"
import { RadioGroup, RadioGroupItem } from "@/components/ui/RadioGroup"
import { DataTablePagination } from "@/components/ui/data-table/DataTablePagination"
import type { DataTableInstance } from "@/components/ui/data-table/dataTableFeatures"
import { FadeIn } from "@/components/ui/motion/FadeIn"
import { ScaleIn } from "@/components/ui/motion/ScaleIn"
import { motion as motionTokens } from "@/theme/tokens"

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

    rerender(<Checkbox aria-label="Select record" checked disabled />)
    expect(input).toBeChecked()
    expect(input).toBeDisabled()
    expect(input.parentElement?.querySelector("div")).toHaveClass("cursor-not-allowed", "grayscale")
    expect(input.parentElement?.querySelector("div")).toHaveStyle({
      opacity: "var(--opacity-medium)",
    })
    expect(input.parentElement?.querySelector("svg path")).toHaveAttribute("d", "M20 6 9 17l-5-5")
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
    expect(() =>
      fireEvent.click(screen.getByRole("checkbox", { name: "No callback" }))
    ).not.toThrow()
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
