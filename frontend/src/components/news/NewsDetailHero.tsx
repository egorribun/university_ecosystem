import { useCallback, useMemo, useState, useEffect } from "react"
import SmartImage from "@/components/media/SmartImage"
import { cn } from "@/utils/cn"
import { useTranslation } from "react-i18next"
import { X as CloseIcon, ZoomIn } from "lucide-react"
import useFocusTrap from "@/hooks/useFocusTrap"

interface NewsDetailHeroProps {
  imageUrl: string
  displayTitle: string
}

export function NewsDetailHero({ imageUrl, displayTitle }: NewsDetailHeroProps) {
  const { t } = useTranslation(["news", "common"])
  const [heroRatio, setHeroRatio] = useState<number | null>(null)
  const [lightboxOpen, setLightboxOpen] = useState(false)

  const lightboxRef = useFocusTrap<HTMLDivElement>({
    active: lightboxOpen,
    onDeactivate: () => setLightboxOpen(false),
  })

  useEffect(() => { setHeroRatio(null) }, [imageUrl])

  const handleHeroLoad = useCallback<React.ReactEventHandler<HTMLImageElement>>((event) => {
    const img = event.currentTarget
    const w = img.naturalWidth || 0
    const h = img.naturalHeight || 0
    if (w && h) setHeroRatio(w / h)
  }, [])

  const heroFrame = useMemo(() => {
    if (!heroRatio || !Number.isFinite(heroRatio) || heroRatio <= 0) {
      return {
        container: "h-(--h-hero-sm) min-h-80 max-h-(--layout-max-modal)",
        image: "object-cover",
        imageStyle: { objectPosition: "50% 40%" },
        backdrop: "bg-(--bg-surface)/(--opacity-dim)",
      }
    }
    const r = Math.min(Math.max(heroRatio, 0.35), 4)
    if (r < 0.82)
      return {
        container: "min-h-(--min-h-hero-lg) max-h-(--h-hero-max-portrait) aspect-3/4",
        image: "object-contain object-center",
        imageStyle: { objectPosition: "center" },
        backdrop: "bg-black/(--opacity-soft)",
      }
    if (r < 1.18)
      return {
        container: "min-h-(--min-h-hero-md) max-h-(--h-hero-max-square) aspect-5/4",
        image: "object-cover",
        imageStyle: { objectPosition: "50% 38%" },
        backdrop: "bg-(--bg-surface)/(--opacity-dim)",
      }
    if (r > 2.6)
      return {
        container: "min-h-(--min-h-hero-xs) max-h-(--h-hero-md) aspect-21/9",
        image: "object-cover",
        imageStyle: { objectPosition: "50% 46%" },
        backdrop: "bg-black/(--opacity-dim)",
      }
    return {
      container: "min-h-(--min-h-hero-sm) max-h-(--h-hero-max-landscape) aspect-video",
      image: "object-cover",
      imageStyle: { objectPosition: "50% 40%" },
      backdrop: "bg-(--bg-surface)/(--opacity-dim)",
    }
  }, [heroRatio])

  return (
    <>
    <figure
      className="relative overflow-hidden rounded-2xl glass-layer-elevated glass-noise border border-glass-border/(--opacity-soft) shadow-glass"
      style={{ viewTransitionName: "news-hero" }}
    >
      <div
        className={cn(
          "flex w-full items-center justify-center overflow-hidden",
          heroFrame.container,
          heroFrame.backdrop
        )}
      >
        <SmartImage
          srcRaw={imageUrl}
          alt={
            displayTitle
              ? t("news:alt.hero", { title: displayTitle })
              : t("news:alt.heroFallback")
          }
          onLoad={handleHeroLoad}
          className={cn("h-full w-full", heroFrame.image)}
          style={heroFrame.imageStyle}
        />
      </div>
      {!displayTitle && (
        <figcaption className="border-t border-glass-border/(--opacity-soft) bg-(--bg-surface)/(--opacity-subtle) px-5 py-3 text-sm font-medium text-(--text-secondary)">
          {t("news:alt.heroFallback")}
        </figcaption>
      )}

      {/* Zoom button */}
      {imageUrl && (
        <button
          type="button"
          onClick={() => setLightboxOpen(true)}
          className="absolute bottom-3 right-3 z-surface inline-flex h-9 w-9 items-center justify-center rounded-xl bg-black/(--opacity-strong) backdrop-blur-sm text-white/(--opacity-heavy) shadow-sm transition hover:bg-black/(--opacity-heavy) hover:scale-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/(--opacity-medium)"
          aria-label={t("news:actions.zoomImage", { defaultValue: "View full image" })}
        >
          <ZoomIn size={16} />
        </button>
      )}
    </figure>

    {/* Lightbox — focus-trapped modal */}
    {lightboxOpen && imageUrl && (
      <div
        ref={lightboxRef}
        className="fixed inset-0 z-modal flex items-center justify-center bg-black/90 backdrop-blur-sm p-4 sm:p-8"
        role="dialog"
        aria-modal
        aria-label={t("news:actions.zoomImage", { defaultValue: "Full image view" })}
        tabIndex={-1}
      >
        {/* Backdrop click to close */}
        {/* eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions */}
        <div className="absolute inset-0" onClick={() => setLightboxOpen(false)} />

        <button
          type="button"
          onClick={() => setLightboxOpen(false)}
          className="absolute top-4 right-4 z-surface inline-flex h-10 w-10 items-center justify-center rounded-full bg-white/(--opacity-dim) text-white transition hover:bg-white/(--opacity-soft) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/(--opacity-medium)"
          aria-label={t("common:buttons.close", { defaultValue: "Close" })}
        >
          <CloseIcon size={20} />
        </button>
        <img
          src={imageUrl}
          alt={displayTitle || t("news:alt.heroFallback")}
          className="relative z-base max-h-[90vh] max-w-[90vw] object-contain rounded-lg select-none"
          draggable={false}
        />
      </div>
    )}
    </>
  )
}
