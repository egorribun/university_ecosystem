import { CSSProperties } from "react"
import { useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"
import { Skeleton, StoryCircle } from "@/components/ui"
import SmartImage from "@/components/SmartImage"
import type { StoryItem } from "@/types/Story"

const SKELETON_COUNT = 8
const STORY_CIRCLE_DIAMETER = "var(--size-story-md)"

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

  if (!shouldShowHeading && !hasStories) return null

  return (
    <div
      data-fade
      style={{ "--fade-delay": "120ms" } as CSSProperties}
      className="flex flex-col gap-(--space-2)"
      aria-busy={loading}
      onPointerEnter={onPrefetch}
      onFocusCapture={onPrefetch}
    >
      {shouldShowHeading && <h2 className="sr-only">{t("stories.heading")}</h2>}
      {loading && (
        <div className="flex flex-wrap gap-(--fluid-gap) py-(--space-3)">
          {Array.from({ length: SKELETON_COUNT }).map((_, index) => (
            <div
              key={index}
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
          className="-mr-(--space-4) flex list-none gap-(--fluid-gap) overflow-x-auto p-0 pr-(--space-4) sm:mr-0 sm:flex-wrap sm:pr-0 [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden"
          aria-label={listLabel}
        >
          {stories.map((story, index) => {
            const label = t("aria.storyItem", { title: story.title })
            const tooltip = story.short_text || story.title
            return (
              <li
                key={story.id}
                className={cn(
                  "flex shrink-0 flex-col items-center justify-center overflow-visible",
                  index === 0 ? "ml-(--space-3) sm:ml-(--space-2)" : ""
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
                  onClick={() => onOpenStory(story, index)}
                  onFocus={onPrefetch}
                  onMouseEnter={onPrefetch}
                  aria-label={label}
                  title={tooltip ?? undefined}
                  data-active={activeStoryId === story.id ? "true" : undefined}
                  className="transition-transform"
                  style={activeStoryId === story.id ? {
                    boxShadow: "0 0 0 var(--space-1) color-mix(in_srgb, var(--brand-main) var(--opacity-medium), transparent)"
                  } : undefined}
                >
                  <div
                    className="relative z-base overflow-hidden rounded-md bg-(--bg-surface-raised) shadow-premium"
                    style={{
                      aspectRatio: "9/16",
                      width: "var(--story-card-w)",
                      ["--story-card-w-md" as string]: "var(--story-card-w-md, 120px)"
                    }}
                  >
                    {story.cover_url ? (
                      <SmartImage
                        srcRaw={story.cover_url}
                        alt={story.title}
                        style={{ width: "100%", height: "100%", borderRadius: "inherit" }}
                      />
                    ) : (
                      <div
                        className="flex h-full w-full items-center justify-center font-bold uppercase tracking-wide"
                        style={{
                          fontSize: "var(--fs-h3)",
                          color: "rgb(255 255 255 / var(--opacity-heavy))"
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
