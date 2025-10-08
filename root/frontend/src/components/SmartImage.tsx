import { useState, memo } from "react"
import { resolveMediaUrl, withCacheBust } from "@/utils/media"

type Props = React.ImgHTMLAttributes<HTMLImageElement> & {
  srcRaw?: string
  cacheV?: number
  fallback?: string
}

export default memo(function SmartImage({ srcRaw, cacheV, fallback, ...rest }: Props) {
  const [err, setErr] = useState(false)
  const raw = srcRaw ?? ""
  const isSpecial = /^blob:/i.test(raw) || /^data:/i.test(raw)
  const resolved = isSpecial ? raw : resolveMediaUrl(raw)
  const base = resolved || fallback || ""
  const src = err
    ? fallback || ""
    : resolved
    ? isSpecial
      ? resolved
      : withCacheBust(resolved, cacheV)
    : base
  return (
    <img
      loading="lazy"
      decoding="async"
      referrerPolicy="no-referrer"
      onError={() => setErr(true)}
      {...rest}
      src={src}
    />
  )
})
