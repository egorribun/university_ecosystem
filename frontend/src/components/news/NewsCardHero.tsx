import SmartImage from "@/components/SmartImage"
import { useOnlineStatus } from "@/hooks/useOnlineStatus"
import { cn } from "@/utils/cn"
import { getMoscowDate } from "@/utils/date"
import dayjs from "dayjs"
import { Cloud, FileText as ArticleIcon } from "lucide-react"
import { memo, useCallback, useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"

interface NewsCardHeroProps {
  image_url?: string
  title?: string
  created_at: string
}

const NewsCardHero = ({ image_url, title, created_at }: NewsCardHeroProps) => {
  const { t } = useTranslation(["news", "common"])
  const isOnline = useOnlineStatus()
  const [cardImageReady, setCardImageReady] = useState(!image_url)

  const cardImageUrl = useMemo(() => image_url || "", [image_url])

  useEffect(() => {
    setCardImageReady(!cardImageUrl)
  }, [cardImageUrl])

  const handleCardImageReady = useCallback(() => setCardImageReady(true), [])

  const createdAtIso = useMemo(
    () => (created_at ? dayjs(created_at).toISOString() : ""),
    [created_at]
  )
  const createdAtLabel = useMemo(() => (created_at ? getMoscowDate(created_at) : ""), [created_at])

  return (
    <div className="relative w-full h-news-hero md:h-news-hero-md shrink-0 overflow-hidden border-b border-glass-border bg-linear-to-br from-brand/(--opacity-subtle) to-brand/(--opacity-faint)">
      <div
        className={cn(
          "absolute inset-0 animate-pulse bg-input-mix transition-opacity duration-base",
          cardImageReady ? "opacity-0" : "opacity-100"
        )}
        aria-hidden
      />
      {cardImageUrl ? (
        <>
          <SmartImage
            srcRaw={cardImageUrl}
            alt={title ? t("news:alt.hero", { title }) : t("news:alt.heroFallback")}
            sizes="(min-width: 1200px) 640px, (min-width: 900px) 520px, 100vw"
            className="absolute inset-0 h-full w-full object-cover transition duration-slower ease-out"
            onLoad={handleCardImageReady}
            onError={handleCardImageReady}
          />
          <div
            className="pointer-events-none absolute inset-0 z-decor transition-opacity duration-base group-hover:opacity-0 bg-linear-to-t from-black/(--opacity-heavy) via-black/(--opacity-medium) to-transparent opacity-strong"
            aria-hidden
          />
        </>
      ) : (
        <span className="relative z-deep flex h-full w-full items-center justify-center overflow-hidden rounded-full">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand/(--opacity-medium) opacity-dim"></span>
          <ArticleIcon className="h-12 w-12" fontSize="large" />
        </span>
      )}

      {/* Badges Overlay */}
      <div className="absolute bottom-3 left-3 z-decor flex flex-wrap gap-2">
        {createdAtIso && (
          <time
            dateTime={createdAtIso}
            className="rounded-full bg-black/(--opacity-strong) px-3 py-1 text-xs font-semibold uppercase tracking-wide text-white/(--opacity-heavy) transition duration-base ease-out group-hover/content:-translate-y-0.5 group-hover/content:bg-black/(--opacity-strong)"
          >
            {createdAtLabel}
          </time>
        )}
        {!isOnline && (
          <div className="flex items-center gap-1 rounded-full bg-warning-bg/(--opacity-heavy) px-2 py-0.5 text-micro font-bold uppercase tracking-wider text-warning-text shadow-surface backdrop-blur-sm">
            <Cloud size={12} />
            <span>{t("common:statuses.cached", { defaultValue: "Кэш" })}</span>
          </div>
        )}
      </div>
    </div>
  )
}

export default memo(NewsCardHero)
