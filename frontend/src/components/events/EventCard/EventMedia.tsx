import { cn } from "@/utils/cn"
import SmartImage from "@/components/media/SmartImage"
import { useTranslation } from "react-i18next"

interface EventMediaProps {
  imageUrl?: string
  alt?: string
  eventType?: string
  timeStatus: {
    status: "live" | "soon" | "none"
    timeText?: string
  }
  isReady: boolean
  onReady: () => void
  onImageClick?: () => void
}

export function EventMedia({
  imageUrl,
  alt,
  eventType,
  timeStatus,
  isReady,
  onReady,
  onImageClick,
}: EventMediaProps) {
  const { t } = useTranslation(["events"])

  return (
    <div className="mb-4">
      <div
        className={cn(
          "relative w-full overflow-hidden rounded-lg",
          "aspect-video max-h-50",
          "bg-linear-to-br from-event-media-tint-from to-event-media-tint-to",
          "border border-event-media-border"
        )}
      >
        <button
          type="button"
          className="block h-full w-full cursor-pointer p-0 border-0 bg-transparent"
          onClick={(e) => {
            e.stopPropagation()
            if (onImageClick) onImageClick()
          }}
          disabled={!onImageClick}
        >
          <SmartImage
            srcRaw={imageUrl}
            alt={alt || t("events:alt.image")}
            sizes="(min-width: 75rem) 25rem, (min-width: 56.25rem) 21.875rem, 100vw"
            className="block h-full w-full object-cover object-center"
            draggable={false}
            onLoad={onReady}
            onError={onReady}
          />
        </button>
        {/* Gradient overlay for depth */}
        <div className="absolute inset-0 bg-linear-to-t from-black/(--opacity-medium) via-transparent to-transparent opacity-medium transition-opacity duration-base group-hover:opacity-strong" />

        {/* Event type badge on image */}
        {eventType && (
          <div className="absolute top-3 left-3 px-3 py-1.5 rounded-lg bg-black/(--opacity-medium) backdrop-blur-md border border-white/(--opacity-dim) shadow-lg">
            <span className="text-xs font-semibold text-[var(--text-inverse)]">{eventType}</span>
          </div>
        )}

        {/* Status indicators */}
        {timeStatus.status === "live" && (
          <div className="absolute top-3 right-3 px-3 py-1.5 rounded-lg bg-success-bg/(--opacity-strong) backdrop-blur-sm shadow-lg flex items-center gap-1.5 text-success-text">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--text-inverse)] opacity-strong" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-[var(--text-inverse)]" />
            </span>
            <span className="text-xs font-bold text-[var(--text-inverse)]">
              {t("common:statuses.live")}
            </span>
          </div>
        )}

        {timeStatus.status === "soon" && timeStatus.timeText && (
          <div className="absolute top-3 right-3 px-3 py-1.5 rounded-lg bg-warning-bg/(--opacity-strong) backdrop-blur-sm shadow-lg flex items-center gap-1.5 text-warning-text">
            <span className="text-xs font-bold text-[var(--text-inverse)]">
              ⏱ {t("events:card.statuses.in", { time: timeStatus.timeText })}
            </span>
          </div>
        )}

        {!isReady && (
          <div className="absolute inset-0 bg-linear-to-br from-event-media-pulse to-(--bg-surface) animate-pulse" />
        )}
      </div>
    </div>
  )
}
