import { useEffect, useMemo, useState, type CSSProperties, type ImgHTMLAttributes } from "react"
import { IMAGE_PLACEHOLDER_URL } from "@/constants/placeholders"
import { addVersionParam, resolveMediaUrl, resolveProxyImageUrl, sanitizeUrl } from "@/utils/media"

const RESPONSIVE_DEFAULT_WIDTHS = [320, 540, 768, 1024, 1440] as const

export type SmartImageProps = {
  srcRaw?: string
  cacheV?: string | number
  fallback?: string
  responsiveWidths?: readonly number[]
} & Omit<ImgHTMLAttributes<HTMLImageElement>, "src">

function buildSrcSet(rawUrl: string, widths: readonly number[]): string {
  if (!sanitizeUrl(rawUrl)) return ""
  const uniqueWidths = Array.from(
    new Set(widths.filter((value) => Number.isFinite(value) && value > 0))
  ).sort((a, b) => a - b)

  if (!uniqueWidths.length) return ""

  return uniqueWidths
    .map((width) => {
      const proxyUrl = resolveProxyImageUrl(rawUrl, width)
      return proxyUrl ? `${proxyUrl} ${width}w` : null
    })
    .filter((src): src is string => src !== null)
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
  const isBlobUrl = srcRaw?.startsWith("blob:")

  const computed = useMemo(() => {
    // We use proxy for all images that are not blobs
    if (isBlobUrl) {
      return sanitizeUrl(srcRaw || "") ? resolveMediaUrl(srcRaw) : ""
    }

    if (!sanitizeUrl(srcRaw || "")) return ""

    // For original src, we don't fix width but still route through proxy for AVIF/WebP
    const resolved = resolveProxyImageUrl(srcRaw)
    if (!resolved) return ""

    return addVersionParam(resolved, cacheV)
  }, [srcRaw, cacheV, isBlobUrl])

  const [useFallback, setUseFallback] = useState(false)

  useEffect(() => {
    // Status tracking removed for production
  }, [computed])

  const finalSrc = useFallback || !computed ? fallback : computed
  const srcSet = useMemo(() => {
    // Don't add srcSet for blob URLs — query params break them
    if (!srcRaw || isBlobUrl) return ""
    return buildSrcSet(srcRaw, responsiveWidths)
  }, [srcRaw, responsiveWidths, isBlobUrl])

  useEffect(() => {
    // Dev logging removed
  }, [finalSrc, useFallback, computed])

  const mergedStyle: CSSProperties = { objectFit: "cover", ...(style ?? {}) }

  return (
    <img
      {...rest}
      alt={alt}
      loading="lazy"
      decoding="async"
      style={mergedStyle}
      src={sanitizeUrl(finalSrc || "") || undefined}
      srcSet={srcSet || undefined}
      sizes={srcSet ? sizes : undefined}
      onLoad={(event) => {
        onLoad?.(event)
      }}
      onError={(event) => {
        if (!useFallback) {
          setUseFallback(true)
        }
        onError?.(event)
      }}
    />
  )
}
