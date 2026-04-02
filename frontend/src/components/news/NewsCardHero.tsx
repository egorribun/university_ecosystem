import SmartImage from "@/components/media/SmartImage"
import { useOnlineStatus } from "@/hooks/useOnlineStatus"
import { cn } from "@/utils/cn"
import { getMoscowDate } from "@/utils/date"
import { getNewsHeroId, clearNewsHeroId } from "@/utils/newsTransition"
import { Cloud, FileText as ArticleIcon } from "lucide-react"
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

interface NewsCardHeroProps {
  id?: string
  image_url?: string
  title?: string
  created_at: string
  featured?: boolean
  /** Set by parent on pointerdown for forward view-transition morphing */
  transitioning?: boolean
}

const NewsCardHero = ({ id, image_url, title, created_at, featured, transitioning }: NewsCardHeroProps) => {
  const { t } = useTranslation(["news", "common"])
  const isOnline = useOnlineStatus()
  const [ready, setReady] = useState(!image_url)
  const containerRef = useRef<HTMLDivElement>(null)

  const src = useMemo(() => image_url || "", [image_url])
  useEffect(() => { setReady(!src) }, [src])

  /* ── Back-nav view transition: set VT name via DOM ref in layout phase ──
     useLayoutEffect fires synchronously after DOM commit but before paint/snapshot.
     Only the FIRST matching card gets the name — clearNewsHeroId() prevents duplicates. */
  useLayoutEffect(() => {
    const el = containerRef.current
    if (!el || !id) return
    const heroId = getNewsHeroId()
    if (heroId !== id) return

    el.style.viewTransitionName = "news-hero"
    clearNewsHeroId()
    return () => { el.style.viewTransitionName = "" }
  }, [id])
  const onLoad = useCallback(() => setReady(true), [])

  const isoDate = useMemo(
    () => (created_at ? new Date(created_at).toISOString() : ""),
    [created_at]
  )
  const label = useMemo(
    () => (created_at ? getMoscowDate(created_at) : ""),
    [created_at]
  )

  /* ── Parallax on scroll — image shifts 15% vertically ── */
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
      { threshold: Array.from({ length: 20 }, (_, i) => i / 19) }
    )

    observer.observe(container)
    return () => observer.disconnect()
  }, [src])

  return (
    <div
      ref={containerRef}
      className="relative h-full w-full overflow-hidden bg-linear-to-br from-brand/(--opacity-subtle) to-transparent"
      style={transitioning ? { viewTransitionName: "news-hero" } : undefined}
    >
      {/* Loading shimmer */}
      <div
        className={cn(
          "absolute inset-0 animate-pulse bg-input-mix transition-opacity duration-base",
          ready ? "opacity-0 pointer-events-none" : "opacity-100"
        )}
        aria-hidden
      />

      {src ? (
        <>
          <SmartImage
            data-parallax-img
            srcRaw={src}
            alt={title ? t("news:alt.hero", { title }) : t("news:alt.heroFallback")}
            sizes={
              featured
                ? "(min-width: 1024px) 55vw, 100vw"
                : "(min-width: 75rem) 33vw, (min-width: 40rem) 50vw, 100vw"
            }
            className="absolute inset-0 h-full w-full object-cover will-change-transform transition-transform duration-slower ease-out scale-[1.12] group-hover:scale-[1.16]"
            onLoad={onLoad}
            onError={onLoad}
          />

          {/* Bottom gradient */}
          <div
            className="pointer-events-none absolute inset-x-0 bottom-0 h-1/2 bg-linear-to-t from-black/(--opacity-heavy) to-transparent"
            aria-hidden
          />
        </>
      ) : (
        <div className="flex h-full w-full items-center justify-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl glass-layer-surface border border-glass-border/(--opacity-soft) text-brand shadow-glass">
            <ArticleIcon className="h-7 w-7" />
          </div>
        </div>
      )}

      {/* Date badge — bottom-left */}
      <div className="absolute bottom-3 left-3 z-decor flex flex-wrap items-center gap-2">
        {isoDate && (
          <time
            dateTime={isoDate}
            className="rounded-full bg-black/(--opacity-strong) backdrop-blur-md px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-white/(--opacity-heavy) shadow-sm"
          >
            {label}
          </time>
        )}
        {!isOnline && (
          <div className="flex items-center gap-1 rounded-full bg-warning-bg/(--opacity-heavy) px-2 py-0.5 text-micro font-bold uppercase tracking-wider text-warning-text backdrop-blur-sm">
            <Cloud size={11} />
            <span>{t("common:statuses.cached", { defaultValue: "Cached" })}</span>
          </div>
        )}
      </div>
    </div>
  )
}

// PERF-27-02: Removed React.memo() — React Compiler "infer" mode handles memoization
export default NewsCardHero
