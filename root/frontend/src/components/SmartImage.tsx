import { useEffect, useMemo, useState, type CSSProperties, type ImgHTMLAttributes } from "react"
import { IMAGE_PLACEHOLDER_URL } from "@/constants/placeholders"
import { addVersionParam, resolveMediaUrl } from "@/utils/media"

const DEV = import.meta.env.DEV === true

const RESPONSIVE_DEFAULT_WIDTHS = [320, 540, 768, 1024, 1440] as const

export type SmartImageProps = {
  srcRaw?: string
  cacheV?: string | number
  fallback?: string
  responsiveWidths?: number[]
} & Omit<ImgHTMLAttributes<HTMLImageElement>, "src">

function buildSrcSet(url: string, widths: number[]): string {
  const uniqueWidths = Array.from(new Set(widths.filter((value) => Number.isFinite(value) && value > 0))).sort(
    (a, b) => a - b
  )

  if (!uniqueWidths.length) return ""

  return uniqueWidths
    .map((width) => {
      try {
        const candidate = new URL(url, window.location.origin)
        candidate.searchParams.set("w", String(width))
        return `${candidate.toString()} ${width}w`
      } catch {
        const separator = url.includes("?") ? "&" : "?"
        return `${url}${separator}w=${encodeURIComponent(width)} ${width}w`
      }
    })
    .join(", ")
}

export default function SmartImage({
  srcRaw,
  cacheV,
  fallback = IMAGE_PLACEHOLDER_URL,
  responsiveWidths = RESPONSIVE_DEFAULT_WIDTHS,
  alt = "",
  style,
  onError,
  onLoad,
  sizes = "(max-width: 720px) 82vw, 460px",
  ...rest
}: SmartImageProps) {
  const computed = useMemo(() => {
    const resolved = resolveMediaUrl(srcRaw)
    if (!resolved) return ""

    // Sanitize URL to prevent XSS
    try {
      const url = new URL(resolved, window.location.origin)
      const protocol = url.protocol.toLowerCase()
      if (protocol === "javascript:" || protocol === "data:" || protocol === "vbscript:") return ""
    } catch {
      // Invalid URL
      return ""
    }

    return addVersionParam(resolved, cacheV)
  }, [srcRaw, cacheV])

  const [useFallback, setUseFallback] = useState(false)

  useEffect(() => {
    setUseFallback(false)
  }, [computed])

  const finalSrc = useFallback || !computed ? fallback : computed
  const srcSet = useMemo(() => {
    if (!computed) return ""
    return buildSrcSet(computed, responsiveWidths)
  }, [computed, responsiveWidths])

  useEffect(() => {
    if (!DEV) return
    const status = useFallback || !computed ? "fallback" : "primary"
    console.info(`[SmartImage] status=${status} src=${finalSrc || "(empty)"}`)
  }, [finalSrc, useFallback, computed])

  const mergedStyle: CSSProperties = { objectFit: "cover", ...(style ?? {}) }

  return (
    <img
      {...rest}
      alt={alt}
      loading="lazy"
      decoding="async"
      style={mergedStyle}
      src={finalSrc}
      srcSet={srcSet || undefined}
      sizes={srcSet ? sizes : undefined}
      onLoad={(event) => {
        if (DEV) {
          console.info(`[SmartImage] status=loaded src=${finalSrc || "(empty)"}`)
        }
        onLoad?.(event)
      }}
      onError={(event) => {
        if (!useFallback) {
          if (DEV) {
            console.warn(`[SmartImage] status=error src=${computed || "(empty)"}`)
          }
          setUseFallback(true)
        } else if (DEV) {
          console.warn(`[SmartImage] status=error src=${fallback || "(empty)"}`)
        }
        onError?.(event)
      }}
    />
  )
}
