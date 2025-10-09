import { memo, useEffect, useMemo, useState, type CSSProperties, type ReactEventHandler } from "react"
import { addVersionParam, resolveMediaUrl } from "@/utils/media"

type Props = React.ImgHTMLAttributes<HTMLImageElement> & {
  srcRaw?: string
  cacheV?: number
  fallback?: string
}

export default memo(function SmartImage({
  srcRaw,
  cacheV,
  fallback,
  style,
  onLoad,
  onError,
  loading,
  alt,
  ...rest
}: Props) {
  const [err, setErr] = useState(false)
  const [loaded, setLoaded] = useState(false)

  const raw = srcRaw ?? ""
  const isSpecial = /^blob:/i.test(raw) || /^data:/i.test(raw)
  const resolved = isSpecial ? raw : resolveMediaUrl(raw)
  const base = resolved || fallback || ""

  useEffect(() => {
    setErr(false)
    setLoaded(false)
  }, [raw, cacheV, fallback])

  const src = useMemo(() => {
    if (err) return fallback || ""
    if (resolved) {
      if (isSpecial) return resolved
      return addVersionParam(resolved, cacheV)
    }
    return base
  }, [base, cacheV, err, fallback, isSpecial, resolved])

  useEffect(() => {
    if (!src) setLoaded(true)
  }, [src])

  const handleLoad: ReactEventHandler<HTMLImageElement> = (event) => {
    setLoaded(true)
    onLoad?.(event)
  }

  const handleError: ReactEventHandler<HTMLImageElement> = (event) => {
    setErr(true)
    setLoaded(true)
    onError?.(event)
  }

  const transition =
    typeof style?.transition === "string"
      ? `${style.transition}, opacity 320ms ease`
      : "opacity 320ms ease"

  const willChange =
    typeof style?.willChange === "string"
      ? style.willChange.includes("opacity")
        ? style.willChange
        : `${style.willChange}, opacity`
      : "opacity"

  const mergedStyle: CSSProperties = {
    ...style,
    transition,
    willChange,
    opacity: loaded ? 1 : 0,
  }

  return (
    <img
      {...rest}
      loading={loading ?? "lazy"}
      decoding="async"
      referrerPolicy="no-referrer"
      onLoad={handleLoad}
      onError={handleError}
      style={mergedStyle}
      src={src}
      alt={alt ?? ""}
      data-loaded={loaded ? "true" : "false"}
      data-has-error={err ? "true" : undefined}
    />
  )
})
