/**
 * SkeletonMorph — Smooth skeleton-to-content transition
 *
 * Instead of replacing skeleton with content (pop-in), the skeleton
 * morphs into content with an opacity dissolve effect.
 *
 * @example
 * ```tsx
 * <SkeletonMorph loaded={!isLoading} skeleton={<CardSkeleton />}>
 *   <CardContent data={data} />
 * </SkeletonMorph>
 * ```
 */

import type { ReactNode } from "react"
import { cn } from "@/utils/cn"

interface SkeletonMorphProps {
  /** Whether content has loaded */
  loaded: boolean
  /** Skeleton placeholder to show while loading */
  skeleton: ReactNode
  /** Actual content to reveal */
  children: ReactNode
  /** Optional className for the container */
  className?: string
}

export function SkeletonMorph({ loaded, skeleton, children, className }: SkeletonMorphProps) {
  return (
    <div className={cn("skeleton-morph-container relative", className)}>
      {/* When loaded: skeleton exits normal flow (absolute) so content height wins.
          FIX-69-10: overflow-hidden when absolute prevents skeleton content from inflating page scroll. */}
      <div
        className={cn("skeleton-morph-skeleton", loaded && "absolute inset-0 overflow-hidden")}
        data-loaded={loaded}
        aria-hidden={loaded}
      >
        {skeleton}
      </div>
      {/* When not loaded: content is absolute (no height contribution) */}
      <div
        className={cn("skeleton-morph-content", !loaded && "absolute inset-0")}
        data-loaded={loaded}
      >
        {loaded ? children : null}
      </div>
    </div>
  )
}
