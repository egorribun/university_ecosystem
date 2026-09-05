import { useMemo, useState, type CSSProperties, type ImgHTMLAttributes } from "react"
import { IMAGE_PLACEHOLDER_URL } from "@/constants/placeholders"
import { addVersionParam, resolveMediaUrl, resolveProxyImageUrl, sanitizeUrl } from "@/utils/media"

const RESPONSIVE_DEFAULT_WIDTHS = [320, 540, 768, 1024, 1440] as const
const NOOP_IMAGE_EVENT = () => undefined

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
  onError = NOOP_IMAGE_EVENT,
  onLoad = NOOP_IMAGE_EVENT,
  sizes = "(max-width: 45rem) 82vw, 28.75rem",
  ...rest
}: SmartImageProps) {
  const isBlobUrl = typeof srcRaw === "string" && srcRaw.startsWith("blob:")

  const computed = useMemo(() => {
    // We use proxy for all images that are not blobs
    if (isBlobUrl) {
      // `isBlobUrl` is derived from a string type guard above, so the value is
      // guaranteed to be present in this branch. Keeping that invariant
      // explicit avoids a dead nullish arm that cannot occur at runtime.
      const blobUrl = srcRaw as string
      return sanitizeUrl(blobUrl) ? resolveMediaUrl(blobUrl) : ""
    }

    if (!sanitizeUrl(srcRaw || "")) return ""

    // For original src, we don't fix width but still route through proxy for AVIF/WebP
    const resolved = resolveProxyImageUrl(srcRaw)
    if (!resolved) return ""

    return addVersionParam(resolved, cacheV)
  }, [srcRaw, cacheV, isBlobUrl])

  const [useFallback, setUseFallback] = useState(false)

  const finalSrc = useFallback || !computed ? fallback : computed
  const srcSet = useMemo(() => {
    // Don't add srcSet for blob URLs — query params break them
    if (!srcRaw || isBlobUrl) return ""
    return buildSrcSet(srcRaw, responsiveWidths)
  }, [srcRaw, responsiveWidths, isBlobUrl])

  const mergedStyle: CSSProperties = { objectFit: "cover", ...(style ?? {}) }

  return (
    <img
      // Wave 112 SW5 — defaults FIRST, `{...rest}` AFTER so callers can
      // override `loading="eager"` + `fetchpriority="high"` for LCP-critical
      // above-the-fold images (Core Web Vitals optimisation). Pre-Wave 112
      // these were forced AFTER spread, silently swallowing caller intent.
      loading="lazy"
      decoding="async"
      {...rest}
      alt={alt}
      style={mergedStyle}
      src={sanitizeUrl(finalSrc || "") || undefined}
      srcSet={srcSet || undefined}
      sizes={srcSet ? sizes : undefined}
      onLoad={(event) => {
        onLoad(event)
      }}
      onError={(event) => {
        // React bails out when the fallback state is already true, so repeated
        // errors from a broken fallback image remain idempotent without an
        // extra branch that can drift from the rendered source.
        setUseFallback(true)
        onError(event)
      }}
    />
  )
}
