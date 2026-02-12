import { useCallback, useId, useMemo, useRef, useState, type KeyboardEvent } from "react"
import { useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"
import { Button, Chip } from "@/components/settings/SettingsUI"
import { getCampusPointsForLocale } from "@/data/campusPoints"
import { ChevronRight, MapPin, RefreshCw, AlertCircle } from "lucide-react"

type MapFallbackReason = "load-error" | "preferences"

interface MapFallbackProps {
  reason: MapFallbackReason
  onRetry?: () => void
}

export default function MapFallback({ reason, onRetry }: MapFallbackProps) {
  const { t, i18n } = useTranslation("system")
  const baseId = useId()
  const instructionsId = `${baseId}-instructions`
  const titleId = `${baseId}-title`
  const listLabelId = `${baseId}-list`

  const campusPointConfigs = useMemo(
    () => getCampusPointsForLocale(i18n.resolvedLanguage ?? i18n.language),
    [i18n.language, i18n.resolvedLanguage]
  )

  const points = useMemo(
    () =>
      campusPointConfigs.map((point) => ({
        key: point.id,
        name: point.title,
        description: point.description,
        address: point.address,
        tags: point.tags.map((tag) => ({
          key: tag,
          label: t(`map.fallback.tags.${tag}`),
        })),
      })),
    [campusPointConfigs, t]
  )

  const [activeIndex, setActiveIndex] = useState(0)
  const itemRefs = useRef<(HTMLDivElement | null)[]>([])

  const focusIndex = useCallback(
    (next: number) => {
      if (next < 0 || next >= points.length) return
      const item = itemRefs.current[next]
      if (item) {
        item.focus()
        setActiveIndex(next)
      }
    },
    [points.length]
  )

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      if (points.length === 0) return
      switch (event.key) {
        case "ArrowDown":
        case "ArrowRight": {
          event.preventDefault()
          const next = (activeIndex + 1) % points.length
          focusIndex(next)
          break
        }
        case "ArrowUp":
        case "ArrowLeft": {
          event.preventDefault()
          const next = (activeIndex - 1 + points.length) % points.length
          focusIndex(next)
          break
        }
        case "Home": {
          event.preventDefault()
          focusIndex(0)
          break
        }
        case "End": {
          event.preventDefault()
          focusIndex(points.length - 1)
          break
        }
        default:
          break
      }
    },
    [activeIndex, focusIndex, points.length]
  )

  return (
    <div
      role="region"
      aria-labelledby={titleId}
      className={cn(
        "absolute inset-0 z-(--z-sticky) overflow-y-auto px-6 py-8 sm:px-12 sm:py-12 flex justify-center",
        "bg-linear-to-br from-background/(--opacity-heavy) to-background/(--opacity-hover) backdrop-blur-3xl",
        "text-(--text-primary)"
      )}
    >
      <div className="w-full max-w-2xl flex flex-col gap-10">
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <h2 id={titleId} className="text-2xl font-black tracking-tight sf-pro">
              {t("map.fallback.title")}
            </h2>
            <p className="text-base font-bold text-(--text-secondary) leading-relaxed">
              {t(`map.fallback.description.${reason === "load-error" ? "load" : "preferences"}`)}
            </p>
          </div>

          <div className="space-y-1 opacity-(--opacity-strong)">
            <p id={instructionsId} className="text-sm font-bold text-(--text-tertiary)">
              {t("map.fallback.instructions")}
            </p>
            <div className="inline-flex items-center gap-2 rounded-sm bg-warning-bg/(--opacity-dim) border border-warning-border/(--opacity-soft) px-3 py-1.5 text-xs font-black text-warning-text uppercase tracking-wider">
              <AlertCircle className="h-3.5 w-3.5" />
              {t("map.fallback.offlineNotice")}
            </div>
          </div>

          {reason === "load-error" && onRetry && (
            <Button
              variant="outline"
              onClick={onRetry}
              className="mt-2 self-start rounded-md h-12 px-8 font-black shadow-lg shadow-brand/(--opacity-subtle)"
              startIcon={<RefreshCw className="h-4 w-4" />}
            >
              {t("map.fallback.retry")}
            </Button>
          )}
        </div>

        <div
          role="listbox"
          tabIndex={0}
          aria-labelledby={listLabelId}
          aria-describedby={instructionsId}
          onKeyDown={handleKeyDown}
          className="flex flex-col gap-4 pb-8 focus:outline-none"
        >
          <p
            id={listLabelId}
            className="text-label-xs font-black uppercase tracking-[0.2em] text-(--text-tertiary) opacity-(--opacity-medium) px-1"
          >
            {t("map.fallback.listLabel")}
          </p>

          {points.map((point, index) => {
            const isActive = index === activeIndex
            return (
              <div
                key={point.key}
                role="option"
                aria-selected={isActive}
                ref={(node: HTMLDivElement | null) => {
                  itemRefs.current[index] = node
                }}
                tabIndex={isActive ? 0 : -1}
                onFocus={() => setActiveIndex(index)}
                onClick={() => focusIndex(index)}
                className={cn(
                  "group relative flex flex-col gap-3 rounded-lg p-6 transition-all duration-500 cursor-pointer outline-none",
                  "border backdrop-blur-xl shadow-glass",
                  isActive
                    ? "border-brand/(--opacity-soft) bg-(--bg-surface-raised)/(--opacity-medium) ring-1 ring-brand/(--opacity-dim) -translate-y-1"
                    : "border-glass-border bg-(--bg-surface)/(--opacity-dim) hover:bg-(--bg-surface)/(--opacity-medium) hover:border-glass-border-hover hover:-translate-y-0.5"
                )}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex flex-col gap-1">
                    <h3 className="text-lg font-black tracking-tight text-(--text-primary) sf-pro">
                      {point.name}
                    </h3>
                    <div className="flex items-center gap-2 text-sm font-bold text-(--text-secondary) opacity-(--opacity-hover)">
                      <MapPin className="h-3.5 w-3.5 shrink-0 text-brand" />
                      {point.address}
                    </div>
                  </div>
                  <div
                    className={cn(
                      "p-2 rounded-md transition-all duration-500",
                      isActive
                        ? "bg-brand text-white shadow-lg shadow-brand/(--opacity-medium)"
                        : "bg-(--bg-surface-hover)/(--opacity-dim) text-(--text-tertiary) opacity-(--opacity-dim) group-hover:opacity-100"
                    )}
                  >
                    <ChevronRight className="h-5 w-5" />
                  </div>
                </div>

                <p className="text-sm font-medium text-(--text-secondary) leading-relaxed opacity-(--opacity-heavy) line-clamp-2">
                  {point.description}
                </p>

                <div className="flex flex-wrap gap-2 pt-2">
                  {point.tags.map((tag) => (
                    <Chip
                      key={tag.key}
                      label={tag.label}
                      className={cn(
                        "rounded-sm border shadow-sm",
                        isActive
                          ? "bg-brand/(--opacity-subtle) border-brand/(--opacity-dim) text-brand"
                          : "bg-(--bg-surface-hover)/(--opacity-subtle) border-glass-border text-(--text-tertiary)"
                      )}
                    />
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
