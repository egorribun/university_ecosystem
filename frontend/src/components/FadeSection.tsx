import type { CSSProperties, HTMLAttributes, ReactNode } from "react"

type FadeSectionProps = HTMLAttributes<HTMLDivElement> & {
  /** Delay value for the fade animation, e.g. "80ms", "140ms" */
  delay: string
  children: ReactNode
}

/**
 * Thin wrapper that encapsulates the repeated `data-fade + fadeDelayStyle` pattern.
 * Replaces 15+ raw `<div data-fade style={{ "--fade-delay": "XXms" }}>` usages.
 *
 * All native `<div>` attributes (role, id, aria-*) are forwarded transparently.
 */
export default function FadeSection({
  delay,
  className,
  children,
  style,
  ...rest
}: FadeSectionProps) {
  return (
    <div
      data-fade
      style={{ "--fade-delay": delay, ...style } as CSSProperties}
      className={className}
      {...rest}
    >
      {children}
    </div>
  )
}
