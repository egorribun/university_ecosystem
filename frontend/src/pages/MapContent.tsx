import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { motion } from "framer-motion"
import {
  ExternalLink as OpenInNewIcon,
  Map as MapIcon,
  Satellite as SatelliteAltIcon,
  RefreshCw as RestartAltIcon,
} from "lucide-react"
import { useTranslation } from "react-i18next"
import MapFallback from "@/components/MapFallback"
import { CAMPUS_COORDINATES } from "@/constants/campus"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"
import { cn } from "@/utils/cn"
import { Button } from "@/components/settings"

type LayerMode = "map" | "hybrid"

const MAP_ID = "128006a9ca6ecba0793cdcd05524ff66e1c0b5187d421dfcae39dd12345e4b57" // trufflehog:ignore
const Z_DEFAULT = 16
const LOAD_TIMEOUT_MS = 12000
/** Vertical offset to hide the Yandex Maps embed branding chrome */
const MAP_IFRAME_OFFSET = "var(--offset-yandex-maps, 45px)"

const detectEmbedOptOut = (): boolean => {
  if (typeof window === "undefined") return false
  try {
    const navigatorWithPrivacy = window.navigator as Navigator & {
      globalPrivacyControl?: boolean
      msDoNotTrack?: string | null
    }
    if (typeof navigatorWithPrivacy.globalPrivacyControl === "boolean") {
      if (navigatorWithPrivacy.globalPrivacyControl) return true
    }
    const doNotTrack =
      navigatorWithPrivacy.doNotTrack ??
      navigatorWithPrivacy.msDoNotTrack ??
      (window as typeof window & { doNotTrack?: string }).doNotTrack
    return doNotTrack === "1" || doNotTrack === "yes"
  } catch {
    return false
  }
}

export default function MapContent() {
  const isMobile = useMediaQuery(`(max-width: ${breakpoints.content})`)
  const { t } = useTranslation("system")
  const [layer, setLayer] = useState<LayerMode>("map")
  const [iframeLoaded, setIframeLoaded] = useState(false)
  const [loadError, setLoadError] = useState(false)
  const [frameKey, setFrameKey] = useState(0)
  const loadSeq = useRef(0)
  const loadTimer = useRef<number | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const iframeLoadedRef = useRef(false)
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")
  const [privacyBlocksEmbeds, setPrivacyBlocksEmbeds] = useState(() => detectEmbedOptOut())

  useEffect(() => {
    const qs = new URLSearchParams(location.search)
    const l = (qs.get("layer") as LayerMode) || "map"
    if (l) setLayer(l)
  }, [])

  useEffect(() => {
    const qs = new URLSearchParams()
    qs.set("layer", layer)
    const url = `${location.pathname}?${qs.toString()}`
    window.history.replaceState(null, "", url)
  }, [layer])

  const lParam = useMemo(() => {
    return layer === "map" ? "map" : "sat,skl"
  }, [layer])

  const mapSrc = useMemo(() => {
    if (layer === "map") {
      return `https://yandex.ru/map-widget/v1/?um=constructor%3A${MAP_ID}&source=constructor`
    }
    const ll = encodeURIComponent(
      `${CAMPUS_COORDINATES.lon.toFixed(6)},${CAMPUS_COORDINATES.lat.toFixed(6)}`
    )
    return `https://yandex.ru/map-widget/v1/?ll=${ll}&z=${Z_DEFAULT}&l=${encodeURIComponent(lParam)}`
  }, [layer, lParam])

  const disableEmbeds = prefersReducedMotion || privacyBlocksEmbeds
  const showFallback = loadError || disableEmbeds
  const fallbackReason = loadError ? "load-error" : disableEmbeds ? "preferences" : null

  const forceReload = useCallback(() => {
    if (disableEmbeds) return
    iframeLoadedRef.current = false
    setIframeLoaded(false)
    setLoadError(false)
    setFrameKey((k) => k + 1)
    loadSeq.current += 1
    if (loadTimer.current) window.clearTimeout(loadTimer.current)
    const seqNow = loadSeq.current
    loadTimer.current = window.setTimeout(() => {
      if (seqNow === loadSeq.current && !iframeLoadedRef.current) setLoadError(true)
    }, LOAD_TIMEOUT_MS)
  }, [disableEmbeds])

  useEffect(() => {
    if (disableEmbeds) {
      iframeLoadedRef.current = false
      setIframeLoaded(false)
      setLoadError(false)
      if (loadTimer.current) window.clearTimeout(loadTimer.current)
      return
    }
    forceReload()
    return () => {
      if (loadTimer.current) window.clearTimeout(loadTimer.current)
    }
  }, [mapSrc, disableEmbeds, forceReload])

  useEffect(() => {
    if (typeof window === "undefined") return
    const handleOptOutChange = () => {
      setPrivacyBlocksEmbeds(detectEmbedOptOut())
    }
    window.addEventListener("focus", handleOptOutChange)
    window.addEventListener("storage", handleOptOutChange)
    return () => {
      window.removeEventListener("focus", handleOptOutChange)
      window.removeEventListener("storage", handleOptOutChange)
    }
  }, [])

  useEffect(() => {
    const computeTop = () => {
      const nav = document.querySelector<HTMLElement>(".navbar-root")
      const h = nav ? Math.round(nav.getBoundingClientRect().height) : 0
      containerRef.current?.style.setProperty("--layout-offset-top", `${Math.max(0, h)}px`)
    }
    computeTop()
    const nav = document.querySelector<HTMLElement>(".navbar-root")
    const ro = window.ResizeObserver ? new ResizeObserver(() => computeTop()) : null
    if (nav && ro) ro.observe(nav)
    window.addEventListener("resize", computeTop)
    window.addEventListener("orientationchange", computeTop)
    return () => {
      ro?.disconnect?.()
      window.removeEventListener("resize", computeTop)
      window.removeEventListener("orientationchange", computeTop)
    }
  }, [])

  const openInYandex = () => {
    if (layer === "map") {
      window.open(
        `https://yandex.ru/maps/?um=constructor:${MAP_ID}&source=constructor`,
        "_blank",
        "noopener,noreferrer"
      )
      return
    }
    const ll = `${CAMPUS_COORDINATES.lon.toFixed(6)},${CAMPUS_COORDINATES.lat.toFixed(6)}`
    window.open(
      `https://yandex.ru/maps/?ll=${ll}&z=${Z_DEFAULT}&l=${lParam.replace(/%2C/g, ",")}`,
      "_blank",
      "noopener,noreferrer"
    )
  }

  const reset = () => {
    if (disableEmbeds) return
    forceReload()
  }

  return (
    <div className="w-full bg-(--bg-surface) text-(--text-primary) rounded-none shadow-2xl overflow-hidden relative">
      <div
        ref={containerRef}
        className="map-page bg-(--bg-canvas-light) dark:bg-(--bg-canvas-dark) transition-colors duration-300 h-full w-full relative"
      >
        <div className="glass glass--panel glass--sheen map-head z-(--z-navbar) flex items-center justify-between px-6 py-4 absolute top-0 left-0 right-0">
          <div className="flex items-center gap-3">
            <MapIcon className={cn("text-brand", isMobile ? "h-6 w-6" : "h-8 w-8")} />
            <h1 className="map-title text-fluid-map-title font-black tracking-tight text-(--text-primary)">
              {t("map.title")}
            </h1>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={openInYandex}
              className="h-10 w-10 p-0 rounded-(--radius-sm) bg-(--bg-surface)/(--opacity-dim) border border-glass-border/(--opacity-dim)"
              title={t("map.openInYandex") ?? ""}
            >
              <OpenInNewIcon className="h-5 w-5" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={reset}
              className="h-10 w-10 p-0 rounded-(--radius-sm) bg-(--bg-surface)/(--opacity-dim) border border-glass-border/(--opacity-dim) text-brand"
              title={t("map.reset") ?? ""}
            >
              <RestartAltIcon className="h-5 w-5" />
            </Button>
          </div>
        </div>

        {!disableEmbeds && (
          <iframe
            key={`${frameKey}`}
            src={mapSrc}
            title={t("map.iframeTitle")}
            width="100%"
            height={`calc(100% + ${MAP_IFRAME_OFFSET})`}
            className={`absolute border-none left-0 right-0 block top-[-${MAP_IFRAME_OFFSET}] bottom-[-${MAP_IFRAME_OFFSET}]`}
            allowFullScreen
            loading="lazy"
            onLoad={() => {
              iframeLoadedRef.current = true
              setIframeLoaded(true)
              setLoadError(false)
              if (loadTimer.current) window.clearTimeout(loadTimer.current)
            }}
          />
        )}

        {(!iframeLoaded || loadError) && !disableEmbeds && (
          <div className="absolute inset-0 z-(--z-sidebar) grid place-items-center bg-background/(--opacity-heavy) backdrop-blur-sm">
            {!loadError ? (
              <div className="h-16 w-16 rounded-full border-4 border-surface/(--opacity-dim) border-t-brand animate-spin" />
            ) : (
              <div className="flex flex-col items-center gap-4">
                <p className="text-sm font-medium text-(--text-secondary)">{t("map.loadError")}</p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setLoadError(false)
                    iframeLoadedRef.current = false
                    setIframeLoaded(false)
                    setFrameKey((k) => k + 1)
                  }}
                >
                  <RestartAltIcon className="h-4 w-4 mr-2" />
                  {t("common:buttons.retry")}
                </Button>
              </div>
            )}
          </div>
        )}

        {showFallback && fallbackReason && (
          <MapFallback
            reason={fallbackReason}
            onRetry={fallbackReason === "load-error" ? forceReload : undefined}
          />
        )}

        <div className="map-controls-shield absolute inset-0 pointer-events-none" />

        <div className="absolute bottom-8 left-1/2 -translate-x-1/2 z-(--z-navbar) pointer-events-none flex flex-col gap-3 pb-(--safe-area-bottom)">
          <div className="flex items-center gap-2 pointer-events-auto">
            <div className="glass glass--panel rounded-(--radius-md) p-1 bg-(--bg-surface)/(--opacity-medium) backdrop-blur-xl border border-glass-border shadow-2xl flex items-center gap-(--space-1)">
              <button
                onClick={() => setLayer("map")}
                className={cn(
                  "relative flex items-center gap-2 rounded-(--radius-sm) px-4 py-2 text-sm font-bold transition-all",
                  layer === "map"
                    ? "text-white"
                    : "text-(--text-secondary) hover:bg-(--bg-surface)/(--opacity-dim)"
                )}
              >
                {layer === "map" && (
                  <motion.div
                    layoutId="map-layer-indicator"
                    className="absolute inset-0 bg-brand rounded-(--radius-sm) shadow-lg shadow-brand/(--opacity-dim)"
                    transition={{ type: "spring", stiffness: 400, damping: 30 }}
                  />
                )}
                <span className="relative z-(--z-base) flex items-center gap-2">
                  <MapIcon className="h-4 w-4" />
                  {!isMobile && <span>{t("map.layer.map")}</span>}
                </span>
              </button>
              <button
                onClick={() => setLayer("hybrid")}
                className={cn(
                  "relative flex items-center gap-2 rounded-(--radius-sm) px-4 py-2 text-sm font-bold transition-all",
                  layer === "hybrid"
                    ? "text-white"
                    : "text-(--text-secondary) hover:bg-(--bg-surface)/(--opacity-dim)"
                )}
              >
                {layer === "hybrid" && (
                  <motion.div
                    layoutId="map-layer-indicator"
                    className="absolute inset-0 bg-brand rounded-(--radius-sm) shadow-lg shadow-brand/(--opacity-dim)"
                    transition={{ type: "spring", stiffness: 400, damping: 30 }}
                  />
                )}
                <span className="relative z-(--z-base) flex items-center gap-2">
                  <SatelliteAltIcon className="h-4 w-4" />
                  {!isMobile && <span>{t("map.layer.hybrid")}</span>}
                </span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
