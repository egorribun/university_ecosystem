import { useRef, useId, useCallback, useEffect, useState } from "react"
import { createPortal } from "react-dom"
import { useTranslation } from "react-i18next"
import { Link } from "@tanstack/react-router"
import { ChevronLeft, ChevronRight, X } from "lucide-react"
import { cn } from "@/utils/cn"
import { Button, ProgressBar } from "@/components/ui"
import SmartImage from "@/components/media/SmartImage"
import type { ButtonProps } from "@/components/ui/Button"
import type { StoryItem } from "@/types/Story"
import { useSwipe } from "@/hooks/useSwipe"
import useFocusTrap from "@/hooks/useFocusTrap"
import useMediaQuery from "@/hooks/useMediaQuery"

const isBrowser = typeof document !== "undefined"

interface StoryViewerProps {
  stories: StoryItem[]
  activeStoryIndex: number | null
  progress: number
  onClose: () => void
  onNext: () => void
  onPrev: () => void
  onPause: () => void
  onResume: () => void
}

export const StoryViewer = ({
  stories,
  activeStoryIndex,
  progress,
  onClose,
  onNext,
  onPrev,
  onPause,
  onResume,
}: StoryViewerProps) => {
  const { t } = useTranslation("dashboard")
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")
  const closeButtonRef = useRef<HTMLButtonElement | null>(null)
  const dialogTitleId = useId()

  const [isClient, setIsClient] = useState(false)
  useEffect(() => setIsClient(true), [])

  const dialogTrapRef = useFocusTrap<HTMLDivElement>({
    active: activeStoryIndex !== null,
    initialFocus: () => closeButtonRef.current ?? undefined,
  })

  useEffect(() => {
    if (!isBrowser || activeStoryIndex === null) return undefined
    const { overflow } = document.body.style
    document.body.style.overflow = "hidden"
    return () => {
      document.body.style.overflow = overflow
    }
  }, [activeStoryIndex])

  const viewerStory = activeStoryIndex === null ? null : (stories[activeStoryIndex] ?? null)

  const progressForIndex = useCallback(
    (index: number) => {
      const currentIndex = activeStoryIndex!
      if (index < currentIndex) return 100
      if (index > currentIndex) return 0
      return progress
    },
    [activeStoryIndex, progress]
  )

  const linkPropsFor = useCallback(
    (url: string): ButtonProps<typeof Link> | ButtonProps<"a"> | null => {
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
        index: activeStoryIndex! + 1,
        total: stories.length,
      })
    : undefined

  const swipeHandlers = useSwipe({
    onSwipeLeft: onNext,
    onSwipeRight: onPrev,
    threshold: 48,
    timeout: 500,
  })

  const handlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      onPause()
      swipeHandlers.onPointerDown(e)
    },
    [swipeHandlers, onPause]
  )

  const handlePointerUp = useCallback(
    (e: React.PointerEvent) => {
      onResume()
      swipeHandlers.onPointerUp(e)
    },
    [swipeHandlers, onResume]
  )

  const handlePointerCancel = useCallback(
    (e: React.PointerEvent) => {
      onResume()
      swipeHandlers.onPointerCancel(e)
    },
    [swipeHandlers, onResume]
  )

  const handlePointerLeave = useCallback(
    (e: React.PointerEvent) => {
      onResume()
      swipeHandlers.onPointerLeave(e)
    },
    [swipeHandlers, onResume]
  )

  if (!isClient || !viewerStory || activeStoryIndex === null) return null

  return createPortal(
    // Wave 54: css-scale-in entrance animation via @starting-style (DESIGN-54-04)
    <div className="css-scale-in fixed inset-0 flex items-center justify-center p-(--fluid-px) z-overlay">
      {/* Wave 54: div with role=presentation, not button (FIX-54-03) */}
      <div
        role="presentation"
        className="pointer-events-auto absolute inset-0 z-base w-full h-full cursor-default bg-linear-to-b from-black/0 via-black/0 to-black/(--opacity-strong)"
        onClick={onClose}
      />
      <div
        ref={dialogTrapRef}
        role="dialog"
        aria-modal="true"
        // Wave 54: prefer aria-labelledby when title exists (FIX-54-04)
        aria-labelledby={viewerStory.title?.trim() ? dialogTitleId : undefined}
        aria-label={viewerStory.title?.trim() ? undefined : storyDialogLabel}
        className="relative z-base flex w-full justify-center"
      >
        {/* Wave 54: Tailwind-only sizing, no conflicting inline styles (FIX-54-05) */}
        <div
          className={cn(
            "relative z-decor flex aspect-9/16 max-h-[92vh] w-[min(96%,960px)] flex-col items-stretch justify-center overflow-hidden text-white sm:aspect-video sm:w-[min(96%,60rem)]",
            viewerStory.cover_url ? "bg-page" : "bg-brand shadow-premium-lift",
            viewerStory.cover_url ? "rounded-none" : "rounded-md sm:rounded-lg"
          )}
          onPointerDown={handlePointerDown}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerCancel}
          onPointerLeave={handlePointerLeave}
        >
          {viewerStory.cover_url ? (
            <SmartImage
              srcRaw={viewerStory.cover_url}
              alt={viewerStory.title}
              className="h-full w-full bg-page object-contain object-center"
            />
          ) : (
            <div className="flex w-full items-center justify-between px-fluid-x">
              <span className="text-(--fs-fluid-display) font-extrabold uppercase">
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
                "p-(--fluid-card-p) pt-12 sm:pt-16"
              )}
              style={{
                backgroundImage: viewerStory.cover_url
                  ? "linear-gradient(180deg, transparent 0%, var(--primary-subtle-bg) 55%, var(--bg-page) 100%)"
                  : "var(--grad-story-fade)",
                backdropFilter: viewerStory.cover_url ? "blur(var(--blur-glass))" : undefined,
                WebkitBackdropFilter: viewerStory.cover_url ? "blur(var(--blur-glass))" : undefined,
              }}
            >
              {viewerStory.title && (
                <h2 id={dialogTitleId} className="text-(--fs-h2) font-extrabold leading-snug">
                  {viewerStory.title}
                </h2>
              )}
              {viewerStory.short_text && (
                <p className="text-base opacity-heavy">{viewerStory.short_text}</p>
              )}
              {viewerStoryLink &&
                ("to" in viewerStoryLink ? (
                  <Button
                    as={Link}
                    to={viewerStoryLink.to}
                    variant="solid"
                    className="self-start rounded-full px-(--space-5)"
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
                    className="self-start rounded-full px-(--space-5)"
                  >
                    {t("stories.viewer.openLink")}
                  </Button>
                ))}
            </div>
          )}

          <div className="absolute left-(--space-4) right-(--space-4) top-(--space-4) flex items-center gap-(--space-2) sm:left-(--space-6) sm:right-(--space-6)">
            {stories.map((story, index) => (
              <ProgressBar
                key={story.id}
                value={progressForIndex(index)}
                ariaLabel={t("stories.viewer.aria.progress", {
                  index: index + 1,
                  total: stories.length,
                  title: story.title,
                })}
                className="h-1 flex-1 bg-white/(--opacity-soft)"
                barClassName={cn(
                  "bg-white",
                  prefersReducedMotion
                    ? "motion-reduce:transition-none"
                    : "duration-rapid ease-linear"
                )}
                animated={!prefersReducedMotion}
                // Wave 54: only active bar announces to screen reader (A11Y-54-01)
                liveRegion={index === activeStoryIndex}
              />
            ))}
          </div>

          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            aria-label={t("stories.viewer.aria.close")}
            className="absolute right-(--space-4) top-(--space-9) inline-flex h-(--space-11) w-(--space-11) items-center justify-center rounded-full bg-glass-bg/(--opacity-medium) text-white transition-colors duration-fast ease-out hover:bg-glass-bg/(--opacity-strong) focus-visible:outline focus-visible:ring-2 focus-visible:ring-white/(--opacity-strong) sm:right-(--space-6)"
          >
            <X size={20} aria-hidden="true" />
          </button>

          <div className="pointer-events-none absolute inset-0">
            <div className="pointer-events-auto absolute left-(--space-2) top-1/2 -translate-y-1/2 sm:left-(--space-6)">
              <button
                type="button"
                onClick={onPrev}
                aria-label={t("stories.viewer.aria.prev")}
                className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-glass-bg/(--opacity-medium) text-white transition-colors duration-fast ease-out hover:bg-glass-bg/(--opacity-strong) focus-visible:outline focus-visible:ring-2 focus-visible:ring-white/(--opacity-strong)"
              >
                <ChevronLeft size={20} aria-hidden="true" />
              </button>
            </div>
            <div className="pointer-events-auto absolute right-2 top-1/2 -translate-y-1/2 sm:right-6">
              <button
                type="button"
                onClick={onNext}
                aria-label={t("stories.viewer.aria.next")}
                className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-glass-bg/(--opacity-medium) text-white transition-colors duration-fast ease-out hover:bg-glass-bg/(--opacity-strong) focus-visible:outline focus-visible:ring-2 focus-visible:ring-white/(--opacity-strong)"
              >
                <ChevronRight size={20} aria-hidden="true" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>,
    document.body
  )
}
