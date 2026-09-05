import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { CSSProperties, ReactEventHandler } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

type SmartImageProps = {
  srcRaw?: string
  alt?: string
  onLoad?: ReactEventHandler<HTMLImageElement>
  className?: string
  style?: CSSProperties
  loading?: "eager" | "lazy"
  fetchPriority?: "high" | "low" | "auto"
}

const translationMocks = vi.hoisted(() => ({
  namespaceCalls: [] as unknown[],
  tCalls: [] as Array<{ key: string; options?: unknown }>,
}))

const smartImageMocks = vi.hoisted(() => ({
  render: vi.fn(),
}))

const focusTrapState = vi.hoisted(() => ({
  calls: [] as Array<{ active: boolean; onDeactivate?: () => void }>,
  onDeactivate: undefined as (() => void) | undefined,
}))

vi.mock("react-i18next", () => ({
  useTranslation: (namespaces: unknown) => {
    translationMocks.namespaceCalls.push(namespaces)
    return {
      t: (key: string, options?: unknown) => {
        translationMocks.tCalls.push({ key, options })
        return key
      },
      i18n: { language: "en", changeLanguage: () => Promise.resolve() },
    }
  },
}))

vi.mock("@/components/media/SmartImage", () => ({
  default: (props: SmartImageProps) => {
    smartImageMocks.render(props)
    return (
      <img
        data-testid="smart-image"
        src={props.srcRaw}
        alt={props.alt}
        className={props.className}
        style={props.style}
        loading={props.loading}
        fetchPriority={props.fetchPriority}
        onLoad={props.onLoad}
      />
    )
  },
}))

vi.mock("@/hooks/useFocusTrap", () => ({
  default: (options: { active: boolean; onDeactivate?: () => void }) => {
    focusTrapState.calls.push(options)
    focusTrapState.onDeactivate = options.onDeactivate
    return { current: null }
  },
}))

import { NewsDetailHero } from "@/components/news/NewsDetailHero"

const baseProps = {
  imageUrl: "https://picsum.photos/seed/news-detail/1200/675",
  displayTitle: "University Announces New AI Research Center",
}

function loadDimensions(image: HTMLElement, width: number, height: number) {
  Object.defineProperty(image, "naturalWidth", { configurable: true, value: width })
  Object.defineProperty(image, "naturalHeight", { configurable: true, value: height })
  fireEvent.load(image)
}

describe("NewsDetailHero mutation contracts", () => {
  beforeEach(() => {
    translationMocks.namespaceCalls = []
    translationMocks.tCalls = []
    smartImageMocks.render.mockClear()
    focusTrapState.calls = []
    focusTrapState.onDeactivate = undefined
  })

  it("preserves exact namespaces, translation interpolation, LCP props, and default frame", () => {
    const { container } = render(<NewsDetailHero {...baseProps} />)

    expect(translationMocks.namespaceCalls).toContainEqual(["news", "common"])
    expect(translationMocks.tCalls).toContainEqual({
      key: "news:alt.hero",
      options: { title: baseProps.displayTitle },
    })

    const figure = container.querySelector("figure")!
    expect(figure).toHaveStyle({ viewTransitionName: "news-hero" })
    const image = screen.getByTestId("smart-image")
    expect(image).toHaveAttribute("alt", "news:alt.hero")
    expect(image).toHaveAttribute("loading", "eager")
    expect(image).toHaveAttribute("fetchpriority", "high")
    expect(image).toHaveClass("h-full", "w-full", "object-cover")
    expect(image).toHaveStyle({ objectPosition: "50% 40%" })
    expect(image.parentElement).toHaveClass(
      "h-(--h-hero-sm)",
      "min-h-80",
      "max-h-(--layout-max-modal)",
      "bg-(--bg-surface)/(--opacity-dim)"
    )
  })

  it("does not derive a ratio from partial image dimensions", () => {
    render(<NewsDetailHero {...baseProps} />)
    const image = screen.getByTestId("smart-image")
    const initialRenderCount = smartImageMocks.render.mock.calls.length

    loadDimensions(image, 0, 800)
    expect(smartImageMocks.render.mock.calls.length).toBe(initialRenderCount)
    expect(image).toHaveClass("object-cover")
    expect(image.parentElement).toHaveClass("max-h-(--layout-max-modal)")

    loadDimensions(image, 800, 0)
    expect(smartImageMocks.render.mock.calls.length).toBe(initialRenderCount)
    expect(image).toHaveClass("object-cover")
  })

  it("uses every responsive frame branch and keeps threshold boundaries stable", () => {
    render(<NewsDetailHero {...baseProps} />)
    const image = screen.getByTestId("smart-image")
    const frame = () => image.parentElement!

    loadDimensions(image, 1, 2)
    expect(frame()).toHaveClass("aspect-3/4", "bg-black/(--opacity-soft)")
    expect(image).toHaveClass("object-contain", "object-center")
    expect(image).toHaveStyle({ objectPosition: "center" })

    loadDimensions(image, 82, 100)
    expect(frame()).toHaveClass("aspect-5/4", "bg-(--bg-surface)/(--opacity-dim)")
    expect(image).toHaveClass("object-cover")
    expect(image).toHaveStyle({ objectPosition: "50% 38%" })

    loadDimensions(image, 118, 100)
    expect(frame()).toHaveClass("aspect-video", "max-h-(--h-hero-max-landscape)")
    expect(image).toHaveClass("object-cover")
    expect(image).toHaveStyle({ objectPosition: "50% 40%" })

    loadDimensions(image, 26, 10)
    expect(frame()).toHaveClass("aspect-video", "bg-(--bg-surface)/(--opacity-dim)")

    loadDimensions(image, 260, 100)
    expect(frame()).toHaveClass("aspect-video", "max-h-(--h-hero-max-landscape)")

    loadDimensions(image, 3, 1)
    expect(frame()).toHaveClass("aspect-21/9", "bg-black/(--opacity-dim)")
    expect(image).toHaveStyle({ objectPosition: "50% 46%" })

    loadDimensions(image, 100, Number.POSITIVE_INFINITY)
    expect(frame()).toHaveClass("h-(--h-hero-sm)", "max-h-(--layout-max-modal)")
    expect(image).toHaveClass("object-cover")

    loadDimensions(image, -1, 5)
    expect(frame()).toHaveClass("h-(--h-hero-sm)", "max-h-(--layout-max-modal)")
    expect(image).toHaveClass("object-cover")
  })

  it("shows the fallback caption and exact lightbox accessibility contract", async () => {
    const user = userEvent.setup()
    render(<NewsDetailHero {...baseProps} displayTitle="" />)

    expect(screen.getByText("news:alt.heroFallback")).toBeInTheDocument()
    const figure = screen.getByTestId("smart-image").closest("figure")!
    expect(figure).toHaveStyle({ viewTransitionName: "news-hero" })
    expect(screen.getByTestId("smart-image")).toHaveAttribute("alt", "news:alt.heroFallback")

    await user.click(screen.getByRole("button", { name: "news:actions.zoomImage" }))
    const lightbox = screen.getByRole("dialog", { name: "news:actions.zoomImage" })
    expect(lightbox).toHaveAttribute("aria-modal", "true")
    expect(lightbox).toHaveAttribute("tabindex", "-1")
    const lightboxImage = screen.getAllByRole("img", { name: "news:alt.heroFallback" })[1]!
    expect(lightboxImage).toHaveAttribute("draggable", "false")
    expect(lightboxImage).toHaveClass("max-h-[90vh]", "max-w-[90vw]", "object-contain")
    expect(focusTrapState.calls.at(-1)?.active).toBe(true)

    focusTrapState.onDeactivate?.()
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
  })

  it("opens and closes the image lightbox from all controls", async () => {
    const user = userEvent.setup()
    render(<NewsDetailHero {...baseProps} />)

    await user.click(screen.getByRole("button", { name: "news:actions.zoomImage" }))
    expect(screen.getByRole("dialog", { name: "news:actions.zoomImage" })).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "common:buttons.close" }))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "news:actions.zoomImage" }))
    const dialog = screen.getByRole("dialog", { name: "news:actions.zoomImage" })
    fireEvent.click(dialog.querySelector("div.absolute.inset-0")!)
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })
})
