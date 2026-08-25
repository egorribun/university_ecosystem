import { memo, CSSProperties, useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"
import { Skeleton, StoryCircle } from "@/components/ui"
import SmartImage from "@/components/media/SmartImage"
import type { StoryItem } from "@/types/Story"

const SKELETON_COUNT = 8
const STORY_CIRCLE_DIAMETER = "var(--size-story-md)"
const FADE_DELAY_MS = 120
const BORDER_WIDTH = 2
/** Minimum pointer movement (px) to count as drag instead of click */
const DRAG_THRESHOLD = 5

type ScrollEdge = "start" | "middle" | "end" | "none"

interface StoryListProps {
  stories: StoryItem[]
  loading?: boolean
  onPrefetch?: () => void
  onOpenStory: (story: StoryItem, index: number) => void
  activeStoryId?: string
}

export const StoryList = memo(function StoryList({
  stories,
  loading = false,
  onPrefetch,
  onOpenStory,
  activeStoryId,
}: StoryListProps) {
  const { t } = useTranslation("dashboard")
  const listLabel = t("aria.storiesList")

  const hasStories = stories.length > 0

  // Drag-to-scroll — ref-based to avoid stale closures
  const listRef = useRef<HTMLUListElement>(null)
  const dragStartX = useRef(0)
  const dragScrollLeft = useRef(0)
  /** True while pointer is held down (ref, not state — needed in pointermove handler) */
  const isPressedRef = useRef(false)
  /** True once movement exceeded threshold in the current press */
  const hasDragged = useRef(false)
  /** Only for cursor styling — useState is fine here */
  const [isDragging, setIsDragging] = useState(false)
  /** Wave 54: Edge fade state for gradient masks (DESIGN-54-01) */
  const [scrollEdge, setScrollEdge] = useState<ScrollEdge>("none")

  // Wave 54: Compute scroll edge for fade masks (DESIGN-54-01)
  const updateScrollEdge = useCallback(() => {
    const el = listRef.current
    if (!el) return
    const { scrollLeft, scrollWidth, clientWidth } = el
    const maxScroll = scrollWidth - clientWidth
    if (maxScroll <= 1) {
      setScrollEdge("none")
      return
    }
    const atStart = scrollLeft <= 1
    const atEnd = scrollLeft >= maxScroll - 1
    if (atStart && atEnd) setScrollEdge("none")
    else if (atStart) setScrollEdge("start")
    else if (atEnd) setScrollEdge("end")
    else setScrollEdge("middle")
  }, [])

  // Wave 54: Wheel→horizontal scroll for mouse users (DESIGN-54-02)
  useEffect(() => {
    const el = listRef.current
    if (!el) return
    const handleWheel = (e: WheelEvent) => {
      // Only intercept vertical wheel (mouse), not trackpad horizontal gesture
      if (e.deltaY === 0 || e.deltaX !== 0) return
      const { scrollLeft, scrollWidth, clientWidth } = el
      const maxScroll = scrollWidth - clientWidth
      if (maxScroll <= 0) return
      // Always prevent page scroll when cursor is over stories list
      e.preventDefault()
      // Clamp scroll within bounds
      const next = scrollLeft + e.deltaY
      el.scrollLeft = Math.max(0, Math.min(next, maxScroll))
    }
    el.addEventListener("wheel", handleWheel, { passive: false })
    return () => el.removeEventListener("wheel", handleWheel)
  }, [loading, hasStories])

  // Wave 54: Track scroll position for edge fades
  useEffect(() => {
    const el = listRef.current
    if (!el) return
    updateScrollEdge()
    el.addEventListener("scroll", updateScrollEdge, { passive: true })
    return () => el.removeEventListener("scroll", updateScrollEdge)
  }, [updateScrollEdge, loading, hasStories])

  // Re-evaluate edge fades on resize (story count or container width may change)
  useEffect(() => {
    const el = listRef.current
    if (!el) return
    const ro = new ResizeObserver(updateScrollEdge)
    ro.observe(el)
    return () => ro.disconnect()
  }, [updateScrollEdge])

  const handlePointerDown = useCallback((e: React.PointerEvent<HTMLUListElement>) => {
    // Wave 54: drag-to-scroll only for mouse — touch uses native overflow-x scroll (FIX-54-09)
    if (e.pointerType !== "mouse" || e.button !== 0) return
    const el = e.currentTarget
    isPressedRef.current = true
    dragStartX.current = e.clientX
    dragScrollLeft.current = el.scrollLeft
    hasDragged.current = false
    // Do NOT setPointerCapture here — that would redirect pointerup away from
    // child <button> elements and break clicks. Capture only after drag threshold.
  }, [])

  const handlePointerMove = useCallback((e: React.PointerEvent<HTMLUListElement>) => {
    if (!isPressedRef.current) return
    const el = e.currentTarget
    const dx = e.clientX - dragStartX.current
    if (Math.abs(dx) > DRAG_THRESHOLD) {
      if (!hasDragged.current) {
        hasDragged.current = true
        setIsDragging(true)
        // Disable snap during drag — snap fights scrollLeft on every frame causing jerk
        el.style.scrollSnapType = "none"
        // Capture only now — threshold exceeded, this is a real drag, not a click
        el.setPointerCapture(e.pointerId)
      }
      e.preventDefault()
      el.scrollLeft = dragScrollLeft.current - dx
    }
  }, [])

  const handlePointerUp = useCallback((e: React.PointerEvent<HTMLUListElement>) => {
    isPressedRef.current = false
    setIsDragging(false)
    const el = listRef.current!
    // Re-enable snap after drag — snaps to nearest story
    el.style.scrollSnapType = ""
    if (el.hasPointerCapture(e.pointerId)) el.releasePointerCapture(e.pointerId)
  }, [])

  const handleStoryClick = useCallback(
    (story: StoryItem, index: number) => {
      if (hasDragged.current) {
        hasDragged.current = false
        return
      }
      onOpenStory(story, index)
    },
    [onOpenStory]
  )

  /** Wave 54: CSS mask for edge fade indicators (DESIGN-54-01) */
  const fadeMaskStyle: CSSProperties | undefined =
    scrollEdge === "start"
      ? {
          maskImage: "linear-gradient(to right, black 85%, transparent 100%)",
          WebkitMaskImage: "linear-gradient(to right, black 85%, transparent 100%)",
        }
      : scrollEdge === "end"
        ? {
            maskImage: "linear-gradient(to left, black 85%, transparent 100%)",
            WebkitMaskImage: "linear-gradient(to left, black 85%, transparent 100%)",
          }
        : scrollEdge === "middle"
          ? {
              maskImage:
                "linear-gradient(to right, transparent 0%, black 10%, black 90%, transparent 100%)",
              WebkitMaskImage:
                "linear-gradient(to right, transparent 0%, black 10%, black 90%, transparent 100%)",
            }
          : undefined

  return (
    <div
      data-fade
      style={{ "--fade-delay": `${FADE_DELAY_MS}ms` } as CSSProperties}
      className="flex flex-col gap-(--space-2)"
      aria-busy={loading}
      onPointerEnter={onPrefetch}
      onFocusCapture={onPrefetch}
    >
      <h2 className="sr-only">{t("stories.heading")}</h2>
      {loading && (
        <div className="flex flex-nowrap gap-(--fluid-gap) py-(--space-3)">
          {Array.from({ length: SKELETON_COUNT }).map((_, index) => (
            <div
              key={`skeleton-${index}`}
              className="shrink-0 flex items-center gap-(--space-2)"
              style={{
                width: STORY_CIRCLE_DIAMETER,
                minHeight: STORY_CIRCLE_DIAMETER,
                minWidth: STORY_CIRCLE_DIAMETER,
                flexBasis: STORY_CIRCLE_DIAMETER,
              }}
            >
              <Skeleton width="100%" height="100%" rounded="full" />
            </div>
          ))}
        </div>
      )}
      {!loading && !hasStories && (
        <div
          role="status"
          className="rounded-xl border border-glass-border/(--opacity-subtle) bg-(--bg-surface)/(--opacity-dim) px-4 py-3"
        >
          <p className="text-sm font-semibold text-text-primary">{t("stories.empty")}</p>
          <p className="mt-1 text-sm text-(--text-secondary)">{t("stories.emptyDescription")}</p>
        </div>
      )}
      {!loading && hasStories && (
        <ul
          ref={listRef}
          className={cn(
            "flex list-none gap-(--fluid-gap) overflow-x-auto p-0 select-none",
            // Wave 54: scroll snap for story-by-story navigation (DESIGN-54-03)
            "snap-x snap-mandatory scroll-pl-0",
            // Hidden scrollbar
            "[scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden",
            isDragging ? "cursor-grabbing" : "cursor-grab"
          )}
          style={fadeMaskStyle}
          aria-label={listLabel}
          onDragStart={(e) => e.preventDefault()}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
          onPointerLeave={handlePointerUp}
        >
          {stories.map((story, index) => {
            const label = t("aria.storyItem", { title: story.title })
            const tooltip = story.short_text || story.title
            return (
              <li
                key={story.id}
                draggable={false}
                // Wave 54: scroll snap align (DESIGN-54-03)
                className="flex shrink-0 snap-start flex-col items-center justify-center overflow-visible"
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
                  borderWidth={BORDER_WIDTH}
                  onClick={() => handleStoryClick(story, index)}
                  onFocus={onPrefetch}
                  onMouseEnter={onPrefetch}
                  aria-label={label}
                  title={tooltip}
                  data-active={activeStoryId === story.id ? "true" : undefined}
                  className="shadow-none transition-opacity"
                  style={
                    activeStoryId === story.id
                      ? {
                          outline: "2px solid currentColor",
                          outlineOffset: "3px",
                        }
                      : undefined
                  }
                >
                  {/* Wave 54: Circular thumbnail — direct image, not a full card (FIX-54-02) */}
                  {story.cover_url ? (
                    <SmartImage
                      srcRaw={story.cover_url}
                      alt={story.title}
                      className="h-full w-full object-cover"
                      // First story = above-the-fold Dashboard LCP candidate (Wave 113 PERF-113-01, SW6 polish).
                      {...(index === 0
                        ? { loading: "eager" as const, fetchPriority: "high" as const }
                        : {})}
                    />
                  ) : (
                    <span
                      className="flex h-full w-full items-center justify-center font-bold uppercase tracking-wide text-white"
                      style={{ fontSize: "var(--fs-fluid-h3)" }}
                    >
                      {story.title.slice(0, 2)}
                    </span>
                  )}
                </StoryCircle>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
})

export default StoryList
