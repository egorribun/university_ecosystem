import { useEffect, useMemo, useState, type CSSProperties, type ImgHTMLAttributes } from "react"
import { IMAGE_PLACEHOLDER_URL } from "@/constants/placeholders"
import { addVersionParam, resolveMediaUrl } from "@/utils/media"

const DEV = import.meta.env.DEV === true

export type SmartImageProps = {
  srcRaw?: string
  cacheV?: string | number
  fallback?: string
} & Omit<ImgHTMLAttributes<HTMLImageElement>, "src">

export default function SmartImage({
  srcRaw,
  cacheV,
  fallback = IMAGE_PLACEHOLDER_URL,
  alt = "",
  style,
  onError,
  onLoad,
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
