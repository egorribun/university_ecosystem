/**
 * ContentCard - Compound component for content cards
 *
 * Provides composable slots for building rich content cards
 * like EventCard and NewsCard with consistent styling.
 *
 * @example
 * ```tsx
 * <ContentCard hoverable onClick={handleClick}>
 *   <ContentCard.Media src={imageUrl} alt={title} />
 *   <ContentCard.Header>
 *     <ContentCard.Title>{title}</ContentCard.Title>
 *     <ContentCard.Actions>
 *       <ActionMenu items={menuItems} />
 *     </ContentCard.Actions>
 *   </ContentCard.Header>
 *   <ContentCard.Body>{description}</ContentCard.Body>
 *   <ContentCard.Footer>
 *     <LikeButton /> <ShareButton />
 *   </ContentCard.Footer>
 * </ContentCard>
 * ```
 */

import {
  memo,
  createContext,
  useContext,
  forwardRef,
  type ReactNode,
  type HTMLAttributes,
  type ImgHTMLAttributes,
} from "react"

import { cn } from "@/utils/cn"
import SmartImage from "@/components/media/SmartImage"
import { Card, type CardProps } from "./Card"

/** Card context for sharing state between compound components */
interface ContentCardContextValue {
  isHovered: boolean
}

const ContentCardContext = createContext<ContentCardContextValue>({
  isHovered: false,
})

export const useContentCardContext = () => useContext(ContentCardContext)

/** Root component props */
interface ContentCardRootProps extends Omit<CardProps, "padding"> {
  children: ReactNode
}

/** Root ContentCard component */
const ContentCardRoot = memo(
  forwardRef<HTMLDivElement, ContentCardRootProps>(({ children, className, ...props }, _ref) => {
    // Note: ref forwarding is not supported by Card component
    // If needed, wrap Card in a div with ref
    return (
      <Card padding="none" className={cn("overflow-hidden", className)} {...props}>
        <ContentCardContext.Provider value={{ isHovered: false }}>
          {children}
        </ContentCardContext.Provider>
      </Card>
    )
  })
)
ContentCardRoot.displayName = "ContentCard"

/** Media slot for images/videos */
interface MediaProps extends ImgHTMLAttributes<HTMLImageElement> {
  aspectRatio?: string
  fallback?: ReactNode
}

const Media = forwardRef<HTMLDivElement, MediaProps>(
  ({ src, alt, aspectRatio = "16/9", fallback, className, ...props }, ref) => {
    if (!src && fallback) {
      return (
        <div
          ref={ref}
          className={cn("relative w-full bg-glass", className)}
          style={{ aspectRatio }}
        >
          {fallback}
        </div>
      )
    }

    return (
      <div
        ref={ref}
        className={cn("relative w-full overflow-hidden", className)}
        style={{ aspectRatio }}
      >
        <SmartImage
          srcRaw={src}
          alt={alt}
          className="h-full w-full object-cover transition-premium group-hover:scale-hover"
          {...props}
        />
      </div>
    )
  }
)
Media.displayName = "ContentCard.Media"

/** Header slot */
interface HeaderProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
}

const Header = forwardRef<HTMLDivElement, HeaderProps>(({ children, className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("flex items-start justify-between gap-2 px-4 pt-4", className)}
    {...props}
  >
    {children}
  </div>
))
Header.displayName = "ContentCard.Header"

/** Title slot */
interface TitleProps extends HTMLAttributes<HTMLHeadingElement> {
  as?: "h1" | "h2" | "h3" | "h4" | "h5" | "h6"
  children: ReactNode
}

const Title = forwardRef<HTMLHeadingElement, TitleProps>(
  ({ as: Component = "h3", children, className, ...props }, ref) => (
    <Component
      ref={ref}
      className={cn("line-clamp-2 text-lg font-semibold text-text-primary", className)}
      {...props}
    >
      {children}
    </Component>
  )
)
Title.displayName = "ContentCard.Title"

/** Actions slot (positioned top-right) */
interface ActionsProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
}

const Actions = forwardRef<HTMLDivElement, ActionsProps>(
  ({ children, className, ...props }, ref) => (
    <div ref={ref} className={cn("shrink-0", className)} {...props}>
      {children}
    </div>
  )
)
Actions.displayName = "ContentCard.Actions"

/** Body slot for main content */
interface BodyProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
}

const Body = forwardRef<HTMLDivElement, BodyProps>(({ children, className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("flex-1 px-4 py-3 text-sm text-(--text-secondary)", className)}
    {...props}
  >
    {children}
  </div>
))
Body.displayName = "ContentCard.Body"

/** Footer slot */
interface FooterProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
}

const Footer = forwardRef<HTMLDivElement, FooterProps>(({ children, className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("flex items-center gap-3 border-t border-border-subtle px-4 py-3", className)}
    {...props}
  >
    {children}
  </div>
))
Footer.displayName = "ContentCard.Footer"

/** Meta info slot (date, category, etc.) */
interface MetaProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
}

const Meta = forwardRef<HTMLDivElement, MetaProps>(({ children, className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      "flex flex-wrap items-center gap-2 px-4 pb-2 text-xs text-(--text-secondary)/(--opacity-hover)",
      className
    )}
    {...props}
  >
    {children}
  </div>
))
Meta.displayName = "ContentCard.Meta"

import { cva, type VariantProps } from "class-variance-authority"

const badgeSlotVariants = cva(
  "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
  {
    variants: {
      variant: {
        default: "bg-(--bg-surface-hover) text-text-primary",
        success: "bg-success-bg text-success-text",
        warning: "bg-warning-bg text-warning-text",
        error: "bg-error-bg text-error-text",
        info: "bg-brand-subtle text-brand",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

/** Badge for status indicators */
interface BadgeSlotProps
  extends HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeSlotVariants> {
  children: ReactNode
}

const BadgeSlot = forwardRef<HTMLSpanElement, BadgeSlotProps>(
  ({ variant, children, className, ...props }, ref) => (
    <span ref={ref} className={cn(badgeSlotVariants({ variant }), className)} {...props}>
      {children}
    </span>
  )
)
BadgeSlot.displayName = "ContentCard.Badge"

/** Compose the compound component */
export const ContentCard = Object.assign(ContentCardRoot, {
  Media,
  Header,
  Title,
  Actions,
  Body,
  Footer,
  Meta,
  Badge: BadgeSlot,
})
