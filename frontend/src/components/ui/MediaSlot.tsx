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
              <svg
                className="h-12 w-12 text-(--text-primary)/(--opacity-dim)"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
                />
              </svg>
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
              <svg
                className="h-12 w-12 text-(--text-tertiary)"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                />
              </svg>
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
            "h-full w-full object-cover transition-all duration-300",
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
