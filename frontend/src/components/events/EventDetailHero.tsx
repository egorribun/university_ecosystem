/**
 * EventDetailHero — hero image with view transition morph + zoom lightbox.
 * Pattern source: components/news/NewsDetailHero.tsx
 */

import SmartImage from "@/components/media/SmartImage"
import { ZoomIn, X } from "lucide-react"
import { useState, useEffect, useMemo, useRef, type SyntheticEvent } from "react"
import { useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"
import useFocusTrap from "@/hooks/useFocusTrap"

interface EventDetailHeroProps {
  imageUrl: string
}

type AspectMode = "landscape" | "portrait" | "square"

/** Focus the lightbox close control when it is still mounted. */
export function focusCloseButton(button: HTMLButtonElement | null): void {
  button?.focus()
}

export function EventDetailHero({ imageUrl }: EventDetailHeroProps) {
  const { t } = useTranslation(["events"])
  const [lightboxOpen, setLightboxOpen] = useState(false)
  const [aspectMode, setAspectMode] = useState<AspectMode>("landscape")

  const handleImageLoad = (e: SyntheticEvent<HTMLImageElement>) => {
    const img = e.currentTarget
    const w = img.naturalWidth || 1
    const h = img.naturalHeight || 1
    const ratio = w / h
    if (ratio < 0.85) setAspectMode("portrait")
    else if (ratio > 1.4) setAspectMode("landscape")
    else setAspectMode("square")
  }

  const closeButtonRef = useRef<HTMLButtonElement>(null)
  const lightboxRef = useFocusTrap<HTMLDivElement>({
    active: lightboxOpen,
    onDeactivate: () => setLightboxOpen(false),
    allowOutsideClick: true,
  })

  // Focus close button when lightbox opens
  useEffect(() => {
    if (lightboxOpen) {
      const timer = setTimeout(() => focusCloseButton(closeButtonRef.current), 50)
      return () => clearTimeout(timer)
    }
  }, [lightboxOpen])

  // Close lightbox on Escape
  useEffect(() => {
    if (!lightboxOpen) return
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setLightboxOpen(false)
    }
    document.addEventListener("keydown", handleEsc)
    return () => document.removeEventListener("keydown", handleEsc)
  }, [lightboxOpen])

  const containerClass = useMemo(() => {
    switch (aspectMode) {
      case "portrait":
        return "aspect-3/4 max-h-[28rem]"
      case "square":
        return "aspect-square max-h-[24rem]"
      default:
        return "aspect-video max-h-[24rem]"
    }
  }, [aspectMode])

  return (
    <>
      {/* Hero image container with view transition */}
      <div
        data-aspect-mode={aspectMode}
        className={cn(
          "relative w-full overflow-hidden rounded-2xl glass-layer-elevated glass-noise border border-glass-border/(--opacity-soft)",
          containerClass
        )}
        style={{ viewTransitionName: "events-hero" }}
      >
        <SmartImage
          srcRaw={imageUrl}
          alt={t("events:alt.image")}
          onLoad={handleImageLoad}
          className={cn(
            "h-full w-full",
            aspectMode === "portrait" ? "object-contain" : "object-cover"
          )}
          // Hero is the LCP candidate on /events/:id — override SmartImage defaults
          // (Wave 113 PERF-113-01, uses Wave 112 SW5 prop ordering).
          loading="eager"
          fetchPriority="high"
        />

        {/* Zoom button */}
        <button
          type="button"
          onClick={() => setLightboxOpen(true)}
          className="absolute bottom-3 right-3 flex h-9 w-9 items-center justify-center rounded-full bg-black/(--opacity-strong) text-[var(--text-inverse)] backdrop-blur-sm transition-transform hover:scale-105 active:scale-95 focus-visible:ring-2 focus-visible:ring-[var(--text-inverse)] focus-visible:ring-offset-2 focus-visible:ring-offset-black"
          aria-label={t("events:detail.actions.zoom")}
        >
          <ZoomIn size={16} />
        </button>
      </div>

      {/* Lightbox modal */}
      {lightboxOpen && (
        // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions, jsx-a11y/click-events-have-key-events -- lightbox backdrop, Escape handled via keydown listener
        <div
          ref={lightboxRef}
          className="fixed inset-0 z-modal flex items-center justify-center bg-black/90 backdrop-blur-sm"
          onClick={() => setLightboxOpen(false)}
          role="dialog"
          aria-modal="true"
          aria-label={t("events:detail.actions.zoom")}
        >
          <button
            ref={closeButtonRef}
            type="button"
            onClick={(event) => {
              event.stopPropagation()
              setLightboxOpen(false)
            }}
            className="absolute top-4 right-4 z-10 flex h-10 w-10 items-center justify-center rounded-full bg-white/(--opacity-dim) text-[var(--text-inverse)] hover:bg-white/(--opacity-soft) transition-colors focus-visible:ring-2 focus-visible:ring-[var(--text-inverse)]"
            aria-label={t("common:buttons.close")}
          >
            <X size={20} />
          </button>
          {/* eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-noninteractive-element-interactions -- lightbox image, keyboard handled by dialog */}
          <img
            src={imageUrl}
            alt={t("events:alt.image")}
            className="max-h-[90vh] max-w-[95vw] rounded-lg object-contain"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </>
  )
}
