import {
  forwardRef,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ComponentProps,
  type CSSProperties,
  type ReactNode,
} from "react"
import { Image as InsertPhotoOutlinedIcon } from "lucide-react"
import { m, AnimatePresence } from "framer-motion"
import { cn } from "@/utils/cn"
import { Skeleton } from "@/components/settings"

import { addVersionParam, resolveProxyImageUrl } from "@/utils/media"
import { useIntersectionObserver } from "@/hooks/useIntersectionObserver"

// IntersectionObserver rootMargin accepts px/% only (NOT rem) — native browsers
// throw `SyntaxError: rootMargin must be specified in pixels or percent` on rem.
// 200px == the prior 12.5rem at a 16px root. Surfaced by the W195 SW6 story smoke
// (AsyncImage is unused in prod + its jsdom test uses a lenient IO mock, so the
// bug stayed latent until a real-browser Storybook render exposed it).
const LAZY_ROOT_MARGIN = "200px"
const NOOP_IMAGE_EVENT = () => undefined
const IMAGE_INITIAL_OPACITY = { opacity: 0 } as const
const IMAGE_TRANSITION = { duration: 0.3 } as const

type Status = "idle" | "loading" | "loaded" | "error"

type AsyncImageProps = ComponentProps<"div"> & {
  src?: string
  alt?: string
  fallbackSrc?: string
  fallback?: ReactNode
  thumbSrc?: string
  objectFit?: CSSProperties["objectFit"]
  version?: number
  onLoad?: ComponentProps<"img">["onLoad"]
  onError?: ComponentProps<"img">["onError"]
}

const AsyncImage = forwardRef<HTMLImageElement, AsyncImageProps>(
  (
    {
      src,
      alt = "",
      fallbackSrc,
      fallback,
      thumbSrc,
      objectFit = "cover",
      version,
      onLoad = NOOP_IMAGE_EVENT,
      onError = NOOP_IMAGE_EVENT,
      className,
      style,
      ...rest
    },
    ref
  ) => {
    const containerRef = useRef<HTMLDivElement>(null)
    const observer = useIntersectionObserver(containerRef, {
      rootMargin: LAZY_ROOT_MARGIN,
      freezeOnceVisible: true,
    })
    const isVisible = !!observer?.isIntersecting

    const [status, setStatus] = useState<Status>(src ? "loading" : "idle")

    const resolvedSrc = useMemo(() => {
      if (!src) return ""
      const proxied = resolveProxyImageUrl(src)
      return version != null ? addVersionParam(proxied, version) : proxied
    }, [src, version])

    useEffect(() => {
      setStatus(resolvedSrc ? "loading" : "idle")
    }, [resolvedSrc])

    const handleLoad: ComponentProps<"img">["onLoad"] = (event) => {
      setStatus("loaded")
      onLoad(event)
    }

    const handleError: ComponentProps<"img">["onError"] = (event) => {
      setStatus("error")
      onError(event)
    }

    const shouldShowSkeleton = status === "loading"
    const shouldShowFallback = status === "error" || (!resolvedSrc && fallback)
    const hasImage = Boolean(resolvedSrc)

    return (
      <div
        ref={containerRef}
        className={cn(
          "relative overflow-hidden rounded-lg bg-(--bg-surface)/(--opacity-subtle)",
          className
        )}
        style={style}
        {...rest}
      >
        <AnimatePresence mode="wait">
          {shouldShowSkeleton && (
            <div
              key="skeleton"
              className="absolute inset-0 z-decor"
              data-testid="async-image-skeleton"
            >
              <Skeleton width="100%" height="100%" />
            </div>
          )}
        </AnimatePresence>

        {thumbSrc && status === "loading" && (
          <img
            src={thumbSrc}
            alt=""
            aria-hidden
            className="absolute inset-0 h-full w-full scale-105 blur-lg block"
            style={{ objectFit }}
          />
        )}

        {hasImage && isVisible && (
          <m.img
            ref={ref}
            key={resolvedSrc}
            src={resolvedSrc}
            alt={alt}
            loading="lazy"
            decoding="async"
            onLoad={handleLoad}
            onError={handleError}
            initial={IMAGE_INITIAL_OPACITY}
            animate={{ opacity: status === "loaded" ? 1 : 0 }}
            transition={IMAGE_TRANSITION}
            className="absolute inset-0 h-full w-full block"
            style={{ objectFit }}
            data-testid="async-image-img"
          />
        )}

        {!hasImage && fallbackSrc && (
          <img
            src={fallbackSrc}
            alt={alt}
            aria-hidden={alt ? undefined : true}
            className="absolute inset-0 h-full w-full block"
            style={{ objectFit }}
          />
        )}

        {((shouldShowFallback && fallback) ||
          status === "error" ||
          (!hasImage && !fallbackSrc)) && (
          <div
            className="absolute inset-0 flex items-center justify-center bg-(--bg-surface)/(--opacity-dim) text-(--text-secondary)"
            data-testid="async-image-fallback"
          >
            {fallback ?? <InsertPhotoOutlinedIcon className="h-10 w-10 opacity-dim shrink-0" />}
          </div>
        )}
      </div>
    )
  }
)

AsyncImage.displayName = "AsyncImage"

export default AsyncImage
