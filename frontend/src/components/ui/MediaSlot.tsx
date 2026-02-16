/**
 * MediaSlot - Lazy-loaded image component with fallback
 *
 * Handles loading states, errors, and aspect ratio.
 *
 * @example
 * ```tsx
 * <MediaSlot
 *   src={imageUrl}
 *   alt={title}
 *   aspectRatio="16/9"
 *   fallback={<ImagePlaceholder />}
 * />
 * ```
 */

import { useState, forwardRef, type ReactNode, type ImgHTMLAttributes } from "react"
import { Image as ImageIcon, ImageOff } from "lucide-react"

import { cn } from "@/utils/cn"

export interface MediaSlotProps extends Omit<
  ImgHTMLAttributes<HTMLImageElement>,
  "onError" | "onLoad"
> {
  /** Aspect ratio (e.g., "16/9", "4/3", "1/1") */
  aspectRatio?: string
  /** Fallback content when no src or on error */
  fallback?: ReactNode
  /** Loading placeholder */
  loadingPlaceholder?: ReactNode
  /** Enable zoom on hover */
  hoverZoom?: boolean
  /** Custom container class */
  containerClassName?: string
  /** Callback when image loads */
  onLoad?: () => void
  /** Callback when image fails to load */
  onError?: () => void
}

export const MediaSlot = forwardRef<HTMLDivElement, MediaSlotProps>(
  (
    {
      src,
      alt,
      aspectRatio = "16/9",
      fallback,
      loadingPlaceholder,
      hoverZoom = true,
      containerClassName,
      className,
      onLoad,
      onError,
      ...props
    },
    ref
  ) => {
    const [isLoading, setIsLoading] = useState(true)
    const [hasError, setHasError] = useState(false)

    const handleLoad = () => {
      setIsLoading(false)
      onLoad?.()
    }

    const handleError = () => {
      setIsLoading(false)
      setHasError(true)
      onError?.()
    }

    // No source - show fallback
    if (!src) {
      return (
        <div
          ref={ref}
          className={cn("relative w-full overflow-hidden bg-(--glass-bg)", containerClassName)}
          style={{ aspectRatio }}
        >
          {fallback ?? (
            <div className="absolute inset-0 flex items-center justify-center">
              <ImageIcon
                className="h-12 w-12 text-text-primary/(--opacity-dim)"
                strokeWidth={1.5}
              />
            </div>
          )}
        </div>
      )
    }

    // Error - show fallback
    if (hasError) {
      return (
        <div
          ref={ref}
          className={cn("relative w-full overflow-hidden bg-(--glass-bg)", containerClassName)}
          style={{ aspectRatio }}
        >
          {fallback ?? (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="flex flex-col items-center gap-2">
                <ImageOff className="h-10 w-10 text-(--text-tertiary)" strokeWidth={1.5} />
              </div>
            </div>
          )}
        </div>
      )
    }

    return (
      <div
        ref={ref}
        className={cn("relative w-full overflow-hidden bg-(--glass-bg)", containerClassName)}
        style={{ aspectRatio }}
      >
        {/* Loading placeholder */}
        {isLoading && (
          <div className="absolute inset-0 animate-pulse bg-(--glass-bg)">
            {loadingPlaceholder ?? (
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="h-8 w-8 animate-spin rounded-full border-2 border-(--primary-main) border-t-transparent" />
              </div>
            )}
          </div>
        )}

        {/* Actual image */}
        <img
          src={src}
          alt={alt}
          loading="lazy"
          onLoad={handleLoad}
          onError={handleError}
          className={cn(
            "h-full w-full object-cover transition-all duration-base",
            isLoading ? "opacity-0" : "opacity-100",
            hoverZoom && "group-hover:scale-105",
            className
          )}
          {...props}
        />
      </div>
    )
  }
)

MediaSlot.displayName = "MediaSlot"
