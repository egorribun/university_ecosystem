/**
 * StaggerChildren — CSS-based stagger wrapper for child elements
 *
 * Uses IntersectionObserver to trigger staggered entrance animations
 * on children. Pure CSS animations with blur dissolve effect.
 *
 * @example
 * ```tsx
 * <StaggerChildren className="grid grid-cols-3 gap-4">
 *   <Card />
 *   <Card />
 *   <Card />
 * </StaggerChildren>
 * ```
 */

import { useRef, useEffect, type ReactNode } from "react"

interface StaggerChildrenProps {
  children: ReactNode
  className?: string
  /** Trigger margin from bottom of viewport (default: -80px) */
  rootMargin?: string
  /** Whether to only trigger once (default: true) */
  once?: boolean
}

export function StaggerChildren({
  children,
  className,
  rootMargin = "0px 0px -80px 0px",
  once = true,
}: StaggerChildrenProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const container = containerRef.current!

    const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches
    if (prefersReduced) {
      const items = container.querySelectorAll<HTMLElement>(".stagger-item")
      items.forEach((item) => {
        item.dataset.visible = "true"
      })
      return
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          const items = container.querySelectorAll<HTMLElement>(".stagger-item")
          items.forEach((item) => {
            item.dataset.visible = "true"
          })
          if (once) observer.disconnect()
        }
      },
      { rootMargin }
    )

    observer.observe(container)
    return () => observer.disconnect()
  }, [rootMargin, once])

  return (
    <div ref={containerRef} className={className}>
      {children}
    </div>
  )
}
