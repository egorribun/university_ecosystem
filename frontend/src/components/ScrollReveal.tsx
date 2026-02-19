import { ReactNode } from "react"
import { useIntersectionObserver } from "@/hooks/ui/useIntersectionObserver"
import { cn } from "@/utils/cn"

type Props = {
  children: ReactNode
  mode?: "fade" | "slide" | "scale" | "pop"
  direction?: "up" | "down" | "left" | "right"
  delay?: number
  duration?: number
  className?: string
  width?: "fit-content" | "100%"
  viewportMargin?: string
}

export const ScrollReveal = ({
  children,
  mode = "slide",
  direction = "up",
  delay = 0,
  duration, // CSS duration handles this, but kept for API compat if needed in future inline styles
  className,
  width = "100%",
  viewportMargin = "0px 0px -50px 0px",
}: Props) => {
  const [ref, isVisible] = useIntersectionObserver({
    rootMargin: viewportMargin,
    freezeOnceVisible: true,
    threshold: 0.1,
  })

  const getHiddenClass = () => {
    if (mode === "fade") return "reveal-hidden-fade"
    if (mode === "scale" || mode === "pop") return "reveal-hidden-scale"

    // Slide direction
    switch (direction) {
      case "up": return "reveal-hidden-slide-up"
      case "down": return "reveal-hidden-slide-up" // Fallback to up for now, or add slide-down if needed
      case "left": return "reveal-hidden-slide-left"
      case "right": return "reveal-hidden-slide-right"
      default: return "reveal-hidden-slide-up"
    }
  }

  return (
    <div
      ref={ref}
      style={{
        width,
        transitionDelay: `${delay}s`,
        transitionDuration: `${duration}s`
      }}
      className={cn(
        "reveal-base",
        isVisible ? "reveal-visible" : getHiddenClass(),
        className
      )}
    >
      {children}
    </div>
  )
}
