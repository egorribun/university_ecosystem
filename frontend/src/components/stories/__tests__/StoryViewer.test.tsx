import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, it, expect, vi } from "vitest"
import { useEffect, type ReactNode } from "react"
import { renderToString } from "react-dom/server"
import { AppShellProvider, useAppShell } from "@/contexts/AppShellContext"
import { StoryViewer } from "../StoryViewer"
import type { StoryItem } from "@/types/Story"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

const motionMocks = vi.hoisted(() => ({ prefersReducedMotion: false }))
const mediaQueryMocks = vi.hoisted(() => ({ queries: [] as string[] }))
const translationMocks = vi.hoisted(() => ({
  namespaces: [] as string[],
  keys: [] as string[],
  dialogOptions: [] as Array<Record<string, unknown> | undefined>,
  progressOptions: [] as Array<Record<string, unknown> | undefined>,
}))
const focusTrapMocks = vi.hoisted(() => ({
  active: [] as boolean[],
  initialFocus: undefined as (() => unknown) | undefined,
  invokeInitialFocusDuringRender: false,
  initialFocusResults: [] as unknown[],
}))
const swipeMocks = vi.hoisted(() => ({
  onPointerDown: vi.fn(),
  onPointerUp: vi.fn(),
  onPointerCancel: vi.fn(),
  onPointerLeave: vi.fn(),
}))

vi.mock("@/hooks/useMediaQuery", () => ({
  default: (query: string) => {
    mediaQueryMocks.queries.push(query)
    return motionMocks.prefersReducedMotion
  },
}))

vi.mock("@/hooks/useFocusTrap", () => ({
  default: ({ active, initialFocus }: { active: boolean; initialFocus?: () => unknown }) => {
    focusTrapMocks.active.push(active)
    focusTrapMocks.initialFocus = initialFocus
    if (focusTrapMocks.invokeInitialFocusDuringRender) {
      focusTrapMocks.initialFocusResults.push(initialFocus?.())
    }
    return { current: null }
  },
}))

vi.mock("react-i18next", () => ({
  useTranslation: (namespace: string) => {
    translationMocks.namespaces.push(namespace)
    return {
      t: (key: string, options?: any) => {
        translationMocks.keys.push(key)
        if (key === "stories.viewer.aria.dialog") {
          translationMocks.dialogOptions.push(options)
          return `Story Viewer: ${options?.title}`
        }
        if (key === "stories.viewer.aria.progress") {
          translationMocks.progressOptions.push(options)
          return `Progress ${options?.index}/${options?.total}: ${options?.title}`
        }
        if (key === "stories.viewer.aria.close") return "Close"
        if (key === "stories.viewer.aria.next") return "Next"
        if (key === "stories.viewer.aria.prev") return "Previous"
        return key
      },
    }
  },
  I18nextProvider: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}))

// Mock useSwipe
vi.mock("@/hooks/useSwipe", () => ({
  useSwipe: () => swipeMocks,
}))

beforeEach(() => {
  vi.clearAllMocks()
  motionMocks.prefersReducedMotion = false
  mediaQueryMocks.queries.length = 0
  translationMocks.namespaces.length = 0
  translationMocks.keys.length = 0
  translationMocks.dialogOptions.length = 0
  translationMocks.progressOptions.length = 0
  focusTrapMocks.active.length = 0
  focusTrapMocks.initialFocus = undefined
  focusTrapMocks.invokeInitialFocusDuringRender = false
  focusTrapMocks.initialFocusResults.length = 0
  document.body.style.overflow = ""
})

const mockStories: StoryItem[] = [
  {
    id: "1",
    title: "Story 1",
    created_at: "2023-01-01",
    expires_at: "2023-01-02",
    published_at: "2023-01-01",
    is_active: true,
    cover_url_optimized: null,
    short_text: "Story 1",
  },
  {
    id: "2",
    title: "Story 2",
    created_at: "2023-01-02",
    expires_at: "2023-01-03",
    published_at: "2023-01-02",
    is_active: true,
    cover_url_optimized: null,
    short_text: "Story 2",
  },
]

// Production always mounts the viewer under the app shell, which owns body
// scroll locking; keep follow-up renders under the same provider.
const withShellRerender = async <T extends { rerender: (ui: ReactNode) => void }>(
  view: Promise<T>
): Promise<T> => {
  const resolved = await view
  const rerender = resolved.rerender
  return {
    ...resolved,
    rerender: (ui: ReactNode) => rerender(<AppShellProvider>{ui}</AppShellProvider>),
  }
}

describe("StoryViewer", () => {
  const defaultProps = {
    stories: mockStories,
    activeStoryIndex: 0,
    progress: 0,
    onClose: vi.fn(),
    onNext: vi.fn(),
    onPrev: vi.fn(),
    onPause: vi.fn(),
    onResume: vi.fn(),
  }

  const renderViewer = (props = {}) => {
    const merged = { ...defaultProps, ...props }
    const Wrapped = () => (
      <AppShellProvider>
        <StoryViewer {...merged} />
      </AppShellProvider>
    )
    return withShellRerender(renderWithRouter({ ui: Wrapped }))
  }

  const renderViewerDirect = (props = {}) => {
    const merged = { ...defaultProps, ...props }
    return render(<StoryViewer {...merged} />, { wrapper: AppShellProvider })
  }

  it("renders nothing when activeStoryIndex is null", async () => {
    const { container } = await renderViewer({ activeStoryIndex: null })
    // TanStack Router renders an <Outlet /> which wraps the ui; even when the
    // tested component returns null the container still has the router shell.
    // Assert the StoryViewer-specific dialog is absent instead.
    expect(container.querySelector("[role='dialog']")).toBeNull()
  })

  it("renders nothing for an out-of-range active story index", async () => {
    const { container } = await renderViewer({ activeStoryIndex: 99 })
    expect(container.querySelector("[role='dialog']")).toBeNull()
  })

  it("is inert during server rendering and uses the browser integration contracts", async () => {
    const serverDocument = globalThis.document
    vi.stubGlobal("document", undefined)
    try {
      expect(
        renderToString(
          <AppShellProvider>
            <StoryViewer {...defaultProps} />
          </AppShellProvider>
        )
      ).toBe("")
    } finally {
      vi.stubGlobal("document", serverDocument)
    }

    await renderViewer()
    expect(translationMocks.namespaces).toContain("dashboard")
    expect(mediaQueryMocks.queries).toContain("(prefers-reduced-motion: reduce)")
    expect(focusTrapMocks.active.at(-1)).toBe(true)
    expect(focusTrapMocks.initialFocus?.()).toBe(screen.getByLabelText("Close"))
  })

  it("keeps initial focus resolution safe before the close button mounts", async () => {
    focusTrapMocks.invokeInitialFocusDuringRender = true

    await renderViewer()

    expect(focusTrapMocks.initialFocusResults).toEqual([undefined])
  })

  it("renders the active story", async () => {
    await renderViewer({ activeStoryIndex: 0 })
    // StoryViewer now uses aria-labelledby pointing to the heading, so the
    // dialog's accessible name is the story title rather than the mocked
    // "Story Viewer: <title>" aria-label key the test originally expected.
    expect(screen.getByRole("dialog", { name: "Story 1" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Story 1" })).toBeInTheDocument()
    const dialog = screen.getByRole("dialog", { name: "Story 1" })
    const describedBy = dialog.getAttribute("aria-describedby")
    expect(describedBy).toBeTruthy()
    expect(document.getElementById(describedBy!)).toHaveTextContent(
      "stories.viewer.aria.instructions"
    )
    const stage = dialog.querySelector('[class*="aspect-9/16"]')
    expect(stage).toHaveClass("landscape:aspect-video")
  })

  it("calls onClose when close button clicked", async () => {
    const user = userEvent.setup()
    const handleClose = vi.fn()
    await renderViewer({ onClose: handleClose })
    await user.click(screen.getByLabelText("Close"))
    expect(handleClose).toHaveBeenCalled()
  })

  it("calls onNext when next button clicked", async () => {
    const user = userEvent.setup()
    const handleNext = vi.fn()
    await renderViewer({ onNext: handleNext })
    await user.click(screen.getByLabelText("Next"))
    expect(handleNext).toHaveBeenCalled()
  })

  it("calls onPrev when prev button clicked", async () => {
    const user = userEvent.setup()
    const handlePrev = vi.fn()
    await renderViewer({ onPrev: handlePrev })
    await user.click(screen.getByLabelText("Previous"))
    expect(handlePrev).toHaveBeenCalled()
  })

  it("renders cover images and resolves internal and external CTA links", async () => {
    const { rerender } = await renderViewer({
      stories: [
        { ...mockStories[0]!, cover_url: "https://cdn.example.com/story.jpg", cta_url: "/events" },
      ],
    })
    expect(screen.getByRole("img", { name: "Story 1" })).toHaveAttribute(
      "src",
      "https://cdn.example.com/story.jpg"
    )
    expect(screen.getByRole("link", { name: "stories.viewer.openLink" })).toHaveAttribute(
      "href",
      "/events"
    )

    rerender(
      <StoryViewer
        {...defaultProps}
        stories={[
          {
            ...mockStories[0]!,
            cover_url: "https://cdn.example.com/story.jpg",
            cta_url: "https://example.com/story",
          },
        ]}
      />
    )
    const externalLink = screen.getByRole("link", { name: "stories.viewer.openLink" })
    expect(externalLink).toHaveAttribute("href", "https://example.com/story")
    expect(externalLink).toHaveAttribute("target", "_blank")
    expect(externalLink).toHaveAttribute("rel", "noreferrer")

    rerender(
      <StoryViewer
        {...defaultProps}
        stories={[{ ...mockStories[0]!, cta_url: "mailto:stories@example.com" }]}
      />
    )
    expect(screen.getByRole("link", { name: "stories.viewer.openLink" })).toHaveAttribute(
      "href",
      "mailto:stories@example.com"
    )
  })

  it("normalizes CTA URLs and preserves the next-story preload contract", async () => {
    await renderViewer({
      stories: [
        { ...mockStories[0]!, cta_url: "  /events  " },
        {
          ...mockStories[1]!,
          cover_url: "https://cdn.example.com/next.jpg",
          cta_url: "HTTPS://example.com/next",
        },
      ],
    })

    expect(screen.getByRole("link", { name: "stories.viewer.openLink" })).toHaveAttribute(
      "href",
      "/events"
    )
    expect(document.querySelector('link[rel="preload"]')).toHaveAttribute(
      "href",
      "https://cdn.example.com/next.jpg"
    )
  })

  it("keeps internal CTA navigation inside the router and rejects non-URL prefixes", async () => {
    const user = userEvent.setup()
    const target = () => <div data-testid="events-target">Events target</div>
    const { rerender } = await withShellRerender(
      renderWithRouter({
        ui: () => (
          <AppShellProvider>
            <StoryViewer {...defaultProps} stories={[{ ...mockStories[0]!, cta_url: "/events" }]} />
          </AppShellProvider>
        ),
        extraRoutes: [{ path: "/events", Component: target }],
      })
    )

    await user.click(screen.getByRole("link", { name: "stories.viewer.openLink" }))
    expect(await screen.findByTestId("events-target")).toBeInTheDocument()

    rerender(
      <StoryViewer
        {...defaultProps}
        stories={[{ ...mockStories[0]!, cta_url: "prefixhttps://example.com" }]}
      />
    )
    const prefixedLink = screen.getByRole("link", { name: "stories.viewer.openLink" })
    expect(prefixedLink).toHaveAttribute("href", "prefixhttps://example.com")
    expect(prefixedLink).not.toHaveAttribute("target", "_blank")
  })

  it("distinguishes HTTP and HTTPS external CTAs while keeping relative links same-window", async () => {
    const { rerender } = await renderViewer({
      stories: [{ ...mockStories[0]!, cta_url: "http://example.com/story" }],
    })
    expect(screen.getByRole("link", { name: "stories.viewer.openLink" })).toHaveAttribute(
      "target",
      "_blank"
    )

    rerender(
      <StoryViewer
        {...defaultProps}
        stories={[{ ...mockStories[0]!, cta_url: "relative/story" }]}
      />
    )
    expect(screen.getByRole("link", { name: "stories.viewer.openLink" })).not.toHaveAttribute(
      "target",
      "_blank"
    )
  })

  it("uses an aria-label when the story has no title and ignores blank CTA urls", async () => {
    await renderViewer({
      stories: [
        {
          ...mockStories[0]!,
          title: "",
          short_text: "Story without a title",
          cta_url: "   ",
        },
      ],
    })
    expect(screen.getByRole("dialog", { name: "Story Viewer:" })).toBeInTheDocument()
    expect(screen.getByText("Story without a title")).toBeInTheDocument()
    expect(screen.queryByRole("link", { name: "stories.viewer.openLink" })).not.toBeInTheDocument()
    expect(document.querySelector('a[href=""]')).not.toBeInTheDocument()
  })

  it("does not throw when an image story has an absent title", async () => {
    await renderViewer({
      stories: [
        {
          ...mockStories[0]!,
          title: undefined as unknown as string,
          cover_url: "https://cdn.example.com/story.jpg",
          short_text: "Accessible fallback",
        },
      ],
    })
    expect(screen.getByRole("dialog", { name: "Story Viewer: undefined" })).toBeInTheDocument()
    expect(screen.getByText("Accessible fallback")).toBeInTheDocument()
  })

  it("assigns completed, active, and pending progress values", async () => {
    const stories = [
      mockStories[0]!,
      mockStories[1]!,
      { ...mockStories[1]!, id: "3", title: "Story 3" },
    ]
    await renderViewer({ stories, activeStoryIndex: 1, progress: 42 })
    const bars = screen.getAllByRole("progressbar")
    expect(bars.map((bar) => bar.getAttribute("aria-valuenow"))).toEqual(["100", "42", "0"])
    expect(bars.map((bar) => bar.getAttribute("aria-label"))).toEqual([
      "Progress 1/3: Story 1",
      "Progress 2/3: Story 2",
      "Progress 3/3: Story 3",
    ])
    expect(bars.map((bar) => bar.getAttribute("aria-live"))).toEqual([null, "polite", null])
    expect(translationMocks.dialogOptions.at(-1)).toMatchObject({
      index: 2,
      total: 3,
      title: "Story 2",
    })
  })

  it("updates progress when the active story or progress changes", async () => {
    const { rerender } = await renderViewer({ progress: 10 })
    expect(screen.getAllByRole("progressbar")[0]).toHaveAttribute("aria-valuenow", "10")

    rerender(
      <StoryViewer
        {...defaultProps}
        activeStoryIndex={1}
        progress={65}
        stories={[
          mockStories[0]!,
          mockStories[1]!,
          { ...mockStories[1]!, id: "3", title: "Story 3" },
        ]}
      />
    )
    expect(
      screen.getAllByRole("progressbar").map((bar) => bar.getAttribute("aria-valuenow"))
    ).toEqual(["100", "65", "0"])
  })

  it("updates progress and scroll locking when the mounted viewer changes stories", async () => {
    const view = renderViewerDirect({ progress: 10 })
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument())
    expect(screen.getAllByRole("progressbar")[0]).toHaveAttribute("aria-valuenow", "10")

    expect(document.body.style.overflow).toBe("hidden")
    view.rerender(<StoryViewer {...defaultProps} activeStoryIndex={1} progress={65} />)

    // Switching stories keeps the one shared lock instead of re-acquiring it.
    expect(document.body.style.overflow).toBe("hidden")
    expect(
      screen.getAllByRole("progressbar").map((bar) => bar.getAttribute("aria-valuenow"))
    ).toEqual(["100", "65"])
  })

  it("uses current interaction callbacks after props change", async () => {
    const firstPause = vi.fn()
    const secondPause = vi.fn()
    const firstResume = vi.fn()
    const secondResume = vi.fn()
    const view = renderViewerDirect({ onPause: firstPause, onResume: firstResume })
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument())

    view.rerender(<StoryViewer {...defaultProps} onPause={secondPause} onResume={secondResume} />)
    const stage = screen.getByRole("dialog").querySelector('[class*="aspect-9/16"]')!
    fireEvent.pointerDown(stage)
    fireEvent.pointerCancel(stage)
    fireEvent.pointerLeave(stage)

    expect(firstPause).not.toHaveBeenCalled()
    expect(firstResume).not.toHaveBeenCalled()
    expect(secondPause).toHaveBeenCalledTimes(1)
    expect(secondResume).toHaveBeenCalledTimes(2)
  })

  it("pauses and resumes around pointer interactions and closes on backdrop", async () => {
    const onClose = vi.fn()
    const onPause = vi.fn()
    const onResume = vi.fn()
    await renderViewer({ onClose, onPause, onResume })
    const dialog = screen.getByRole("dialog")
    const stage = dialog.querySelector('[class*="aspect-9/16"]')!

    fireEvent.pointerDown(stage)
    fireEvent.pointerUp(stage)
    fireEvent.pointerCancel(stage)
    fireEvent.pointerLeave(stage)
    expect(onPause).toHaveBeenCalledTimes(1)
    expect(onResume).toHaveBeenCalledTimes(3)
    expect(swipeMocks.onPointerDown).toHaveBeenCalledTimes(1)
    expect(swipeMocks.onPointerUp).toHaveBeenCalledTimes(1)
    expect(swipeMocks.onPointerCancel).toHaveBeenCalledTimes(1)
    expect(swipeMocks.onPointerLeave).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole("presentation"))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it("uses reduced-motion progress settings", async () => {
    motionMocks.prefersReducedMotion = true
    await renderViewer({ progress: 35 })
    const bar = screen.getAllByRole("progressbar")[0]!
    expect(bar.firstElementChild?.className).toContain("motion-reduce:transition-none")
    expect(bar.firstElementChild).not.toHaveClass("transition-all")
    expect(bar).toHaveAttribute("aria-live", "polite")
  })

  it("exposes the progress styling, overlay spacing, and image backdrop contracts", async () => {
    const firstRender = await renderViewer({
      stories: [{ ...mockStories[0]!, cover_url: "https://cdn.example.com/story.jpg" }],
    })
    const imageStage = screen.getByRole("dialog").querySelector('[class*="aspect-9/16"]')!
    const imageOverlay = imageStage.querySelector('[class*="absolute bottom-0"]')!
    expect(imageOverlay).toHaveClass("gap-4", "p-(--fluid-card-p)", "pt-12", "sm:pt-16")
    expect(imageOverlay).toHaveStyle({ backdropFilter: "blur(var(--blur-glass))" })
    expect(screen.getAllByRole("progressbar")[0]!.firstElementChild).toHaveClass(
      "bg-white",
      "transition-all",
      "duration-rapid",
      "ease-linear"
    )

    firstRender.unmount()
    await renderViewer({ stories: [{ ...mockStories[0]!, cta_url: "/events" }] })
    const textOverlay = screen.getByRole("dialog").querySelector('[class*="absolute bottom-0"]')!
    expect(textOverlay).toHaveClass("gap-5")
  })

  it("omits an empty short-text paragraph while retaining populated text", async () => {
    const { rerender } = await renderViewer({
      stories: [{ ...mockStories[0]!, short_text: "" }],
    })
    expect(screen.queryByText("Story 1", { selector: "p.text-base" })).not.toBeInTheDocument()

    rerender(
      <StoryViewer {...defaultProps} stories={[{ ...mockStories[0]!, short_text: "Details" }]} />
    )
    expect(screen.getByText("Details", { selector: "p.text-base" })).toBeInTheDocument()
  })

  it("locks body scrolling and restores the previous value when closed", async () => {
    document.body.style.overflow = "scroll"
    const { rerender } = await renderViewer()
    expect(document.body.style.overflow).toBe("hidden")

    rerender(<StoryViewer {...defaultProps} activeStoryIndex={null} />)
    expect(document.body.style.overflow).toBe("scroll")
  })

  it("renders the visual and accessibility variants for image and text stories", async () => {
    const { rerender } = await renderViewer({
      stories: [{ ...mockStories[0]!, cover_url: "https://cdn.example.com/story.jpg" }],
    })
    const imageDialog = screen.getByRole("dialog", { name: "Story 1" })
    const imageStage = imageDialog.querySelector('[class*="aspect-9/16"]')!
    expect(imageStage).toHaveClass("bg-page", "rounded-none")
    const imageOverlay = imageStage.querySelector('[class*="absolute bottom-0"]')!
    expect(imageOverlay).toHaveStyle({
      backgroundImage:
        "linear-gradient(180deg, transparent 0%, var(--primary-subtle-bg) 55%, var(--bg-page) 100%)",
      backdropFilter: "blur(var(--blur-glass))",
    })

    rerender(
      <StoryViewer
        {...defaultProps}
        stories={[{ ...mockStories[0]!, title: "Fallback", short_text: "", cover_url: null }]}
      />
    )
    const textDialog = screen.getByRole("dialog", { name: "Fallback" })
    const textStage = textDialog.querySelector('[class*="aspect-9/16"]')!
    expect(textStage).toHaveClass("bg-brand", "rounded-md")
    const textOverlay = textStage.querySelector('[class*="absolute bottom-0"]')!
    expect(textOverlay).toHaveStyle({ backgroundImage: "var(--grad-story-fade)" })
    expect(screen.getByText("FA")).toBeInTheDocument()
  })

  it("keeps the labelled-by fallback and overlay branches explicit", async () => {
    await renderViewer({
      stories: [{ ...mockStories[0]!, title: "   ", short_text: "Only body", cta_url: null }],
    })
    const dialog = screen.getByRole("dialog", { name: "Story Viewer:" })
    expect(dialog).not.toHaveAttribute("aria-labelledby")
    expect(dialog).toHaveAttribute("aria-label", "Story Viewer:    ")
    expect(screen.getByText("Only body")).toBeInTheDocument()
  })

  it("omits the copy overlay when a story has no title, text, or CTA", async () => {
    await renderViewer({
      stories: [{ ...mockStories[0]!, title: "", short_text: "", cta_url: null }],
    })
    const dialog = screen.getByRole("dialog", { name: "Story Viewer:" })
    expect(dialog.querySelector('[class*="bottom-0"]')).not.toBeInTheDocument()
  })

  it("shares the app-shell scroll lock with other overlays instead of owning body overflow", () => {
    const OtherOverlay = ({ locked }: { locked: boolean }) => {
      const { setOverlayState } = useAppShell()
      useEffect(() => {
        setOverlayState("other-overlay", locked ? { blurred: false, scrollLocked: true } : null)
      }, [locked, setOverlayState])
      return null
    }
    const Shell = ({
      locked,
      activeStoryIndex,
    }: {
      locked: boolean
      activeStoryIndex: number | null
    }) => (
      <AppShellProvider>
        <OtherOverlay locked={locked} />
        <StoryViewer {...defaultProps} activeStoryIndex={activeStoryIndex} />
      </AppShellProvider>
    )

    const { rerender } = render(<Shell locked activeStoryIndex={null} />)
    expect(document.body.style.overflow).toBe("hidden")
    rerender(<Shell locked activeStoryIndex={0} />)
    rerender(<Shell locked={false} activeStoryIndex={0} />)
    // The story is still open, so releasing the other overlay keeps the lock.
    expect(document.body.style.overflow).toBe("hidden")
    rerender(<Shell locked={false} activeStoryIndex={null} />)
    expect(document.body.style.overflow).toBe("")
  })
})
