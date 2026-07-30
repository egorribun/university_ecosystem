/**
 * EventCardHero — image section with parallax, shimmer, date badge,
 * LIVE indicator, view transition morph support.
 * Pattern source: components/news/NewsCardHero.tsx
 */

import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"
import SmartImage from "@/components/media/SmartImage"
import { useOnlineStatus } from "@/hooks/useOnlineStatus"
import { cn } from "@/utils/cn"
import { formatDate, formatRelativeTime } from "@/utils/date"
import { getEventsHeroId, clearEventsHeroId } from "@/utils/eventsTransition"
import { Calendar, Cloud, CalendarDays } from "lucide-react"
import { useTranslation } from "react-i18next"

interface EventCardHeroProps {
  id?: string
  imageUrl?: string
  title?: string
  startsAt: string
  endsAt?: string
  /** "live" | "soon" | "none" — computed by parent */
  timeStatus?: "live" | "soon" | "none"
  /** Set by parent on pointerdown for forward view-transition morphing */
  transitioning?: boolean
  /** First card in grid — promotes hero image to LCP candidate (Wave 113 PERF-113-01) */
  priority?: boolean
}

const EventCardHero = ({
  id,
  imageUrl,
  title,
  startsAt,
  endsAt: _endsAt,
  timeStatus = "none",
  transitioning,
  priority,
}: EventCardHeroProps) => {
  const { t, i18n } = useTranslation(["events", "common"])
  const isOnline = useOnlineStatus()
  const [ready, setReady] = useState(!imageUrl)
  const containerRef = useRef<HTMLDivElement>(null)

  const src = useMemo(() => imageUrl || "", [imageUrl])
  useEffect(() => {
    setReady(!src)
  }, [src])

  /* ── Back-nav view transition: set VT name via DOM ref in layout phase ──
     Same pattern as NewsCardHero — useLayoutEffect fires synchronously
     after DOM commit but before paint/snapshot. */
  useLayoutEffect(() => {
    const el = containerRef.current
    if (!el || !id) return
    const heroId = getEventsHeroId()
    if (heroId !== id) return

    el.style.viewTransitionName = "events-hero"
    clearEventsHeroId()

    const cleanup = setTimeout(() => {
      el.style.viewTransitionName = ""
    }, 0)
    return () => {
      clearTimeout(cleanup)
      el.style.viewTransitionName = ""
    }
  }, [id])

  const onLoad = useCallback(() => setReady(true), [])

  /* ── Date formatting ── */
  const locale = i18n.language === "ru" ? "ru-RU" : "en-US"
  const dateLabel = useMemo(
    () =>
      startsAt
        ? formatDate(startsAt, {
            day: "numeric",
            month: "short",
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
          })
        : "",
    [startsAt]
  )
  const relativeLabel = useMemo(
    () => (startsAt ? formatRelativeTime(startsAt, locale) : ""),
    [startsAt, locale]
  )
  const isoDate = useMemo(() => (startsAt ? new Date(startsAt).toISOString() : ""), [startsAt])

  /* ── Parallax on scroll — image shifts 8% vertically ── */
  useEffect(() => {
    const container = containerRef.current
    if (!container || !src) return

    const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches
    if (prefersReduced) return

    const img = container.querySelector<HTMLElement>("[data-parallax-img]")
    if (!img) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry) return
        // Map intersectionRatio [0,1] → translateY [8%, -8%]
        const shift = (1 - entry.intersectionRatio * 2) * 8
        img.style.transform = `translateY(${shift}%) scale(1.12)`
      },
      { threshold: [0, 0.25, 0.5, 0.75, 1] }
    )

    observer.observe(container)
    return () => observer.disconnect()
  }, [src])

  return (
    <div
      ref={containerRef}
      className="relative h-full w-full overflow-hidden bg-linear-to-br from-brand/(--opacity-subtle) to-transparent"
      style={transitioning ? { viewTransitionName: "events-hero" } : undefined}
    >
      {/* Loading shimmer */}
      <div
        className={cn(
          "absolute inset-0 animate-pulse bg-input-mix transition-opacity duration-base",
          ready ? "opacity-0 pointer-events-none" : "opacity-100"
        )}
        aria-hidden="true"
      />

      {src ? (
        <>
          <SmartImage
            data-parallax-img
            srcRaw={src}
            alt={title ? t("events:alt.image") : ""}
            sizes="(min-width: 75rem) 25vw, (min-width: 40rem) 33vw, 100vw"
            className="absolute inset-0 h-full w-full object-cover will-change-transform transition-transform duration-slower ease-out scale-[1.12] group-hover:scale-[1.16]"
            onLoad={onLoad}
            onError={onLoad}
            // First-card LCP override (Wave 113 PERF-113-01).
            {...(priority ? { loading: "eager" as const, fetchPriority: "high" as const } : {})}
          />

          {/* Bottom gradient */}
          <div
            className="pointer-events-none absolute inset-x-0 bottom-0 h-1/2 bg-linear-to-t from-black/(--opacity-heavy) to-transparent"
            aria-hidden="true"
          />
        </>
      ) : (
        <div className="flex h-full w-full items-center justify-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl glass-layer-surface border border-glass-border/(--opacity-soft) text-brand shadow-glass">
            <CalendarDays className="h-7 w-7" />
          </div>
        </div>
      )}

      {/* Status badges — top-right */}
      {timeStatus === "live" && (
        <div className="absolute top-3 right-3 z-surface flex items-center gap-1.5 rounded-full bg-error-bg px-2.5 py-1 text-[10px] font-bold uppercase tracking-widest text-error-text shadow-sm">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-error-text opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-error-text" />
          </span>
          {t("events:card.statuses.live")}
        </div>
      )}
      {timeStatus === "soon" && (
        <div className="absolute top-3 right-3 z-surface flex items-center gap-1 rounded-full bg-warning-bg px-2.5 py-1 text-[10px] font-bold uppercase tracking-widest text-warning-text shadow-sm">
          <Calendar size={10} />
          {t("events:card.statuses.soon")}
        </div>
      )}

      {/* Date badge — bottom-left */}
      <div className="absolute bottom-3 left-3 z-decor flex flex-wrap items-center gap-2">
        {isoDate && (
          <time
            dateTime={isoDate}
            title={dateLabel}
            className="events-badge-matte rounded-full px-3 py-1 text-[11px] font-semibold tracking-wider"
          >
            {relativeLabel}
          </time>
        )}
        {!isOnline && (
          <div className="flex items-center gap-1 rounded-full bg-warning-bg/(--opacity-heavy) px-2 py-0.5 text-micro font-bold uppercase tracking-wider text-warning-text backdrop-blur-sm">
            <Cloud size={11} />
            <span>{t("common:statuses.cached")}</span>
          </div>
        )}
      </div>
    </div>
  )
}

export default memo(EventCardHero)
