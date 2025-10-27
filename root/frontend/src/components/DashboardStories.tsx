import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useId,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
  type SVGProps,
} from "react"
import { createPortal } from "react-dom"
import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import SmartImage from "@/components/SmartImage"
import { Button, ProgressBar, Skeleton, StoryCircle, STORY_CIRCLE_SIZE_MAP } from "@/components/ui"
import type { ButtonProps } from "@/components/ui/button"
import type { StoryItem } from "@/types/Story"
import useFocusTrap from "@/hooks/useFocusTrap"
import useMediaQuery from "@/hooks/useMediaQuery"
import { cn } from "@/utils/cn"

const STORY_AUTO_ADVANCE_MS = 6500
const SKELETON_COUNT = 8
const STORY_CIRCLE_DIAMETER = STORY_CIRCLE_SIZE_MAP.md

const isBrowser = typeof document !== "undefined"

type DashboardStoriesProps = {
  stories: StoryItem[]
  loading?: boolean
  onPrefetch?: () => void
  onStoryOpen?: (story: StoryItem) => void
  maxVisibleStories?: number
}

export default function DashboardStories({
  stories,
  loading = false,
  onPrefetch,
  onStoryOpen,
  maxVisibleStories = 12,
}: DashboardStoriesProps) {
  const { t } = useTranslation("dashboard")
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")

  const [isClient, setIsClient] = useState(false)
  useEffect(() => setIsClient(true), [])

  const listLabel = t("aria.storiesList")

  const displayStories = useMemo(() => {
    const filtered = Array.isArray(stories) ? stories.filter(Boolean) : []
    return filtered.slice(0, Math.max(1, maxVisibleStories))
  }, [stories, maxVisibleStories])

  const [openIndex, setOpenIndex] = useState<number | null>(null)
  const [progress, setProgress] = useState(0)
  const [isPaused, setIsPaused] = useState(false)
  const touchOrigin = useRef<{ x: number; y: number } | null>(null)
  const rafRef = useRef<number | null>(null)
  const autoStartRef = useRef<number>(0)
  const closeButtonRef = useRef<HTMLButtonElement | null>(null)

  const dialogTrapRef = useFocusTrap<HTMLDivElement>({
    active: openIndex !== null,
    initialFocus: () => closeButtonRef.current ?? undefined,
  })

  useEffect(() => {
    return () => {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    if (!isBrowser || openIndex === null) return undefined
    const { overflow } = document.body.style
    document.body.style.overflow = "hidden"
    return () => {
      document.body.style.overflow = overflow
    }
  }, [openIndex])

  const closeViewer = useCallback(() => {
    setOpenIndex(null)
    setProgress(0)
  }, [])

  const goToIndex = useCallback(
    (nextIndex: number | null) => {
      if (nextIndex === null) {
        closeViewer()
        return
      }
      const next = Math.max(0, Math.min(displayStories.length - 1, nextIndex))
      setProgress(0)
      setOpenIndex(next)
      if (displayStories[next]) {
        onStoryOpen?.(displayStories[next])
      }
    },
    [closeViewer, displayStories, onStoryOpen]
  )

  const goNext = useCallback(() => {
    if (openIndex === null) return
    if (openIndex >= displayStories.length - 1) {
      closeViewer()
      return
    }
    goToIndex(openIndex + 1)
  }, [openIndex, displayStories.length, goToIndex, closeViewer])

  const goPrev = useCallback(() => {
    if (openIndex === null) return
    if (openIndex <= 0) {
      setProgress(0)
      return
    }
    goToIndex(openIndex - 1)
  }, [openIndex, goToIndex])

  useEffect(() => {
    if (openIndex === null) {
      setProgress(0)
      return
    }
    setProgress(0)
    autoStartRef.current = performance.now()
  }, [openIndex])

  useEffect(() => {
    if (openIndex === null || prefersReducedMotion || isPaused) {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
      return
    }

    const step = (timestamp: number) => {
      const elapsed = timestamp - autoStartRef.current
      const ratio = Math.min(1, elapsed / STORY_AUTO_ADVANCE_MS)
      setProgress(ratio * 100)
      if (ratio >= 1) {
        rafRef.current = null
        goNext()
        return
      }
      rafRef.current = requestAnimationFrame(step)
    }

    rafRef.current = requestAnimationFrame(step)

    return () => {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
    }
  }, [openIndex, goNext, prefersReducedMotion, isPaused])

  useEffect(() => {
    if (openIndex === null) return
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault()
        closeViewer()
      }
      if (event.key === "ArrowRight") {
        event.preventDefault()
        goNext()
      }
      if (event.key === "ArrowLeft") {
        event.preventDefault()
        goPrev()
      }
    }
    window.addEventListener("keydown", handleKey)
    return () => window.removeEventListener("keydown", handleKey)
  }, [openIndex, closeViewer, goNext, goPrev])

  const dialogTitleId = useId()

  const progressForIndex = useCallback(
    (index: number) => {
      if (openIndex === null) return 0
      if (index < openIndex) return 100
      if (index > openIndex) return 0
      return progress
    },
    [openIndex, progress]
  )

  const renderAvatar = useCallback((story: StoryItem) => {
    if (story.cover_url) {
      return (
        <SmartImage
          srcRaw={story.cover_url}
          alt={story.title}
          style={{ width: "100%", height: "100%", borderRadius: "inherit" }}
        />
      )
    }
    const initials = story.title.slice(0, 2).toUpperCase()
    return (
      <div className="flex h-full w-full items-center justify-center text-[1.1rem] font-semibold uppercase tracking-wide text-white/95">
        {initials}
      </div>
    )
  }, [])

  const openStory = useCallback(
    (story: StoryItem, index: number) => {
      autoStartRef.current = performance.now()
      setProgress(0)
      setOpenIndex(index)
      onStoryOpen?.(story)
    },
    [onStoryOpen]
  )

  const viewerStory = openIndex === null ? null : (displayStories[openIndex] ?? null)

  const linkPropsFor = useCallback(
    (url?: string | null): ButtonProps<typeof Link> | ButtonProps<"a"> | null => {
      if (!url) return null
      const trimmed = url.trim()
      if (!trimmed) return null
      if (trimmed.startsWith("/")) {
        return { as: Link, to: trimmed } satisfies ButtonProps<typeof Link>
      }
      if (/^https?:/i.test(trimmed)) {
        return {
          as: "a" as const,
          href: trimmed,
          target: "_blank",
          rel: "noreferrer" as const,
        } satisfies ButtonProps<"a">
      }
      return { as: "a" as const, href: trimmed } satisfies ButtonProps<"a">
    },
    []
  )

  const viewerStoryLink = viewerStory?.cta_url ? linkPropsFor(viewerStory.cta_url) : null

  const storyDialogLabel = viewerStory
    ? t("stories.viewer.aria.dialog", {
        title: viewerStory.title,
        index: (openIndex ?? 0) + 1,
        total: displayStories.length,
      })
    : undefined

  const hasStories = displayStories.length > 0
  const shouldShowHeading = loading || hasStories

  const handlePointerStart = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    touchOrigin.current = { x: event.clientX, y: event.clientY }
    setIsPaused(true)
  }, [])

  const handlePointerEnd = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      const origin = touchOrigin.current
      touchOrigin.current = null
      setIsPaused(false)
      if (!origin) return
      const dx = event.clientX - origin.x
      const dy = event.clientY - origin.y
      if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 48) {
        if (dx < 0) {
          goNext()
        } else {
          goPrev()
        }
        return
      }
      if ((event.target as HTMLElement).closest("button,a")) {
        return
      }
      goNext()
    },
    [goNext, goPrev]
  )

  const overlay =
    isClient && viewerStory && openIndex !== null
      ? createPortal(
          <div
            className="fixed inset-0 flex items-center justify-center p-4 sm:p-8"
            style={{ zIndex: "var(--ue-z-index-overlay)" }}
          >
            <div
              aria-hidden
              className="absolute inset-0 bg-[rgba(8,11,21,0.35)] backdrop-blur-xl"
              onClick={closeViewer}
            />
            <div
              ref={dialogTrapRef}
              role="dialog"
              aria-modal="true"
              aria-labelledby={viewerStory.title ? dialogTitleId : undefined}
              aria-label={storyDialogLabel}
              className="relative z-[1] flex w-full justify-center"
            >
              <div
                className={cn(
                  "relative flex aspect-[9/16] w-[min(92vw,420px)] max-h-[92vh] max-w-[min(92vw,420px)] flex-col items-stretch justify-center overflow-hidden text-white sm:aspect-[16/9] sm:w-[min(96vw,960px)] sm:max-h-[80vh] sm:max-w-[min(96vw,960px)]",
                  viewerStory.cover_url
                    ? "bg-[#080b15]"
                    : "bg-[linear-gradient(135deg,#1d4ed8,#60a5fa)] shadow-[0_30px_80px_rgba(0,0,0,0.55)]",
                  viewerStory.cover_url ? "rounded-none" : "rounded-[1.25rem] sm:rounded-[1.5rem]"
                )}
                onPointerDown={handlePointerStart}
                onPointerUp={handlePointerEnd}
                onPointerCancel={() => {
                  touchOrigin.current = null
                  setIsPaused(false)
                }}
                onPointerLeave={() => {
                  touchOrigin.current = null
                  setIsPaused(false)
                }}
              >
                {viewerStory.cover_url ? (
                  <SmartImage
                    srcRaw={viewerStory.cover_url}
                    alt={viewerStory.title}
                    style={{
                      width: "100%",
                      height: "100%",
                      objectFit: "contain",
                      objectPosition: "center",
                      backgroundColor: "#080b15",
                    }}
                  />
                ) : (
                  <div className="flex flex-1 items-center justify-center bg-[linear-gradient(135deg,#1d4ed8,#60a5fa)]">
                    <span className="text-[clamp(2.2rem,12vw,3.2rem)] font-extrabold uppercase">
                      {viewerStory.title.slice(0, 2).toUpperCase()}
                    </span>
                  </div>
                )}

                <p className="sr-only">{t("stories.viewer.hints.auto")}</p>

                {(viewerStory.title || viewerStory.short_text || viewerStory.cta_url) && (
                  <div
                    className={cn(
                      "absolute bottom-0 left-0 right-0 flex flex-col",
                      viewerStory.cta_url ? "gap-5" : "gap-4",
                      "p-6 pt-12 sm:p-8 sm:pt-16"
                    )}
                    style={{
                      backgroundImage: viewerStory.cover_url
                        ? "linear-gradient(180deg, rgba(8,11,21,0) 0%, rgba(8,11,21,0.65) 55%, rgba(8,11,21,0.85) 100%)"
                        : "linear-gradient(180deg, rgba(15,23,42,0) 0%, rgba(15,23,42,0.82) 60%, rgba(15,23,42,0.95) 100%)",
                      backdropFilter: viewerStory.cover_url ? "blur(12px)" : undefined,
                      WebkitBackdropFilter: viewerStory.cover_url ? "blur(12px)" : undefined,
                    }}
                  >
                    {viewerStory.title && (
                      <h2 id={dialogTitleId} className="text-3xl font-extrabold leading-snug">
                        {viewerStory.title}
                      </h2>
                    )}
                    {viewerStory.short_text && (
                      <p className="text-base opacity-95">{viewerStory.short_text}</p>
                    )}
                    {viewerStoryLink &&
                      ("to" in viewerStoryLink ? (
                        <Button
                          as={Link}
                          to={viewerStoryLink.to}
                          variant="solid"
                          className="self-start rounded-full px-5"
                        >
                          {t("stories.viewer.openLink")}
                        </Button>
                      ) : (
                        <Button
                          as="a"
                          href={viewerStoryLink.href}
                          target={viewerStoryLink.target}
                          rel={viewerStoryLink.rel}
                          variant="solid"
                          className="self-start rounded-full px-5"
                        >
                          {t("stories.viewer.openLink")}
                        </Button>
                      ))}
                  </div>
                )}

                <div className="absolute left-4 right-4 top-3 flex items-center gap-2 sm:left-6 sm:right-6 sm:top-4">
                  {displayStories.map((story, index) => (
                    <ProgressBar
                      key={story.id}
                      value={progressForIndex(index)}
                      ariaLabel={t("stories.viewer.aria.progress", {
                        index: index + 1,
                        total: displayStories.length,
                        title: story.title,
                      })}
                      className="h-[3px] flex-1 bg-white/35"
                      barClassName={cn(
                        "bg-white",
                        prefersReducedMotion
                          ? "motion-reduce:transition-none"
                          : "duration-150 ease-linear"
                      )}
                      animated={!prefersReducedMotion}
                    />
                  ))}
                </div>

                <button
                  ref={closeButtonRef}
                  type="button"
                  onClick={closeViewer}
                  aria-label={t("stories.viewer.aria.close")}
                  className="absolute right-4 top-9 inline-flex h-11 w-11 items-center justify-center rounded-full bg-[rgba(8,11,21,0.55)] text-white transition-colors duration-200 ease-out hover:bg-[rgba(8,11,21,0.7)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white/70 sm:right-6"
                >
                  <CloseIcon className="h-5 w-5" aria-hidden="true" />
                </button>

                <div className="pointer-events-none absolute inset-0">
                  <div className="pointer-events-auto absolute left-2 top-1/2 -translate-y-1/2 sm:left-6">
                    <button
                      type="button"
                      onClick={goPrev}
                      aria-label={t("stories.viewer.aria.prev")}
                      className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-[rgba(8,11,21,0.55)] text-white transition-colors duration-200 ease-out hover:bg-[rgba(8,11,21,0.7)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white/70"
                    >
                      <ArrowLeftIcon className="h-5 w-5" aria-hidden="true" />
                    </button>
                  </div>
                  <div className="pointer-events-auto absolute right-2 top-1/2 -translate-y-1/2 sm:right-6">
                    <button
                      type="button"
                      onClick={goNext}
                      aria-label={t("stories.viewer.aria.next")}
                      className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-[rgba(8,11,21,0.55)] text-white transition-colors duration-200 ease-out hover:bg-[rgba(8,11,21,0.7)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white/70"
                    >
                      <ArrowRightIcon className="h-5 w-5" aria-hidden="true" />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>,
          document.body
        )
      : null

  return (
    <>
      <div
        data-fade
        style={{ "--fade-delay": "120ms" } as CSSProperties}
        className="flex flex-col gap-2"
        aria-busy={loading}
        onPointerEnter={onPrefetch}
        onFocusCapture={onPrefetch}
      >
        {shouldShowHeading && <h2 className="sr-only">{t("stories.heading")}</h2>}
        {loading && (
          <div className="flex flex-wrap gap-x-6 gap-y-6 py-3">
            {Array.from({ length: SKELETON_COUNT }).map((_, index) => (
              <div
                key={index}
                className="flex flex-shrink-0 flex-col items-center justify-center"
                style={{
                  width: STORY_CIRCLE_DIAMETER,
                  minHeight: STORY_CIRCLE_DIAMETER,
                  minWidth: STORY_CIRCLE_DIAMETER,
                  flexBasis: STORY_CIRCLE_DIAMETER,
                }}
              >
                <Skeleton width={STORY_CIRCLE_DIAMETER} height={STORY_CIRCLE_DIAMETER} rounded="9999px" />
              </div>
            ))}
          </div>
        )}
        {!loading && hasStories && (
          <ul
            className="-mr-4 flex list-none gap-6 overflow-x-auto p-0 pr-4 sm:-mr-0 sm:flex-wrap sm:pr-0 [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden"
            aria-label={listLabel}
          >
            {displayStories.map((story, index) => {
              const label = t("aria.storyItem", { title: story.title })
              const tooltip = story.short_text || story.title
              return (
                <li
                  key={story.id}
                  className={cn(
                    "flex flex-shrink-0 flex-col items-center justify-center overflow-visible",
                    index === 0 ? "ml-3 sm:ml-2" : ""
                  )}
                  style={{
                    width: STORY_CIRCLE_DIAMETER,
                    minHeight: STORY_CIRCLE_DIAMETER,
                    minWidth: STORY_CIRCLE_DIAMETER,
                    flexBasis: STORY_CIRCLE_DIAMETER,
                  }}
                >
                  <StoryCircle
                    as="button"
                    type="button"
                    size="md"
                    borderWidth={2}
                    onClick={() => openStory(story, index)}
                    onFocus={onPrefetch}
                    onMouseEnter={onPrefetch}
                    aria-label={label}
                    title={tooltip ?? undefined}
                    data-active={viewerStory?.id === story.id ? "true" : undefined}
                    className={cn(
                      "transition-transform data-[active=true]:ring-4 data-[active=true]:ring-[rgba(125,172,255,0.45)]"
                    )}
                  >
                    <div className="relative h-full w-full overflow-hidden rounded-full">
                      {renderAvatar(story)}
                    </div>
                  </StoryCircle>
                </li>
              )
            })}
          </ul>
        )}
      </div>
      {overlay}
    </>
  )
}

function CloseIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      <path d="M18 6 6 18" />
      <path d="M6 6l12 12" />
    </svg>
  )
}

function ArrowLeftIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      <path d="M15 18l-6-6 6-6" />
    </svg>
  )
}

function ArrowRightIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      <path d="M9 6l6 6-6 6" />
    </svg>
  )
}
