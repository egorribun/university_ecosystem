import { CSSProperties, useCallback, useRef, useState } from "react"
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

interface StoryListProps {
  stories: StoryItem[]
  loading?: boolean
  onPrefetch?: () => void
  onOpenStory: (story: StoryItem, index: number) => void
  activeStoryId?: string
}

export const StoryList = ({
  stories,
  loading = false,
  onPrefetch,
  onOpenStory,
  activeStoryId,
}: StoryListProps) => {
  const { t } = useTranslation("dashboard")
  const listLabel = t("aria.storiesList")

  const hasStories = stories.length > 0
  const shouldShowHeading = loading || hasStories

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

  const handlePointerDown = useCallback((e: React.PointerEvent<HTMLUListElement>) => {
    if (e.pointerType === "mouse" && e.button !== 0) return
    const el = listRef.current
    if (!el) return
    isPressedRef.current = true
    dragStartX.current = e.clientX
    dragScrollLeft.current = el.scrollLeft
    hasDragged.current = false
    // Do NOT setPointerCapture here — that would redirect pointerup away from
    // child <button> elements and break clicks. Capture only after drag threshold.
  }, [])

  const handlePointerMove = useCallback((e: React.PointerEvent<HTMLUListElement>) => {
    if (!isPressedRef.current) return
    const el = listRef.current
    if (!el) return
    const dx = e.clientX - dragStartX.current
    if (Math.abs(dx) > DRAG_THRESHOLD) {
      if (!hasDragged.current) {
        hasDragged.current = true
        setIsDragging(true)
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
    const el = listRef.current
    if (el?.hasPointerCapture(e.pointerId)) el.releasePointerCapture(e.pointerId)
  }, [])

  const handleStoryClick = useCallback((story: StoryItem, index: number) => {
    if (hasDragged.current) {
      hasDragged.current = false
      return
    }
    onOpenStory(story, index)
  }, [onOpenStory])

  if (!shouldShowHeading && !hasStories) return null

  return (
    <div
      data-fade
      style={{ "--fade-delay": `${FADE_DELAY_MS}ms` } as CSSProperties}
      className="flex flex-col gap-(--space-2)"
      aria-busy={loading}
      onPointerEnter={onPrefetch}
      onFocusCapture={onPrefetch}
    >
      {shouldShowHeading && <h2 className="sr-only">{t("stories.heading")}</h2>}
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
      {!loading && hasStories && (
        <ul
          ref={listRef}
          className={cn(
            "flex list-none gap-(--fluid-gap) overflow-x-auto p-0 [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden select-none",
            isDragging ? "cursor-grabbing" : "cursor-grab"
          )}
          aria-label={listLabel}
          style={{ touchAction: "pan-y" }}
          onDragStart={e => e.preventDefault()}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
        >
          {stories.map((story, index) => {
            const label = t("aria.storyItem", { title: story.title })
            const tooltip = story.short_text || story.title
            return (
              <li
                key={story.id}
                draggable={false}
                className="flex shrink-0 flex-col items-center justify-center overflow-visible"
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
                  title={tooltip ?? undefined}
                  data-active={activeStoryId === story.id ? "true" : undefined}
                  className="transition-transform"
                  style={
                    activeStoryId === story.id
                      ? {
                          boxShadow:
                            "0 0 0 var(--space-1) color-mix(in_srgb, var(--brand-main) var(--opacity-medium), transparent)",
                        }
                      : undefined
                  }
                >
                  <div className="relative z-base aspect-9/16 w-[--story-card-w] overflow-hidden rounded-md bg-(--bg-surface-raised) shadow-premium md:w-[--story-card-w-md]">
                    {story.cover_url ? (
                      <SmartImage
                        srcRaw={story.cover_url}
                        alt={story.title}
                        className="h-full w-full rounded-[inherit]"
                      />
                    ) : (
                      <div
                        className="flex h-full w-full items-center justify-center font-bold uppercase tracking-wide"
                        style={{
                          fontSize: "var(--fs-h3)",
                          color: "rgb(255 255 255 / var(--opacity-heavy))",
                        }}
                      >
                        {story.title.slice(0, 2).toUpperCase()}
                      </div>
                    )}
                  </div>
                </StoryCircle>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
