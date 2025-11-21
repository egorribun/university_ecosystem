import { ReactNode } from "react"
import { cn } from "../utils/cn"

type LayoutProps = {
  children: ReactNode
  className?: string
}

const Layout = ({ children, className }: LayoutProps) => (
  <main
    id="main"
    className={cn(
      "box-border min-h-screen w-full bg-[var(--page-bg)] text-[var(--page-text)]",
      className
    )}
  >
    {children}
  </main>
)

export default Layout
