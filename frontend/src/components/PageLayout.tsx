import { ReactNode } from "react"
import Layout from "./Layout"
import PageFadeIn from "./PageFadeIn"
import { cn } from "@/utils/cn"

type PageLayoutVariant = "default" | "wide" | "narrow" | "full"

interface PageLayoutProps {
  children: ReactNode
  className?: string
  variant?: PageLayoutVariant
}

const variants: Record<PageLayoutVariant, string> = {
  default: "px-fluid-x max-w-(--layout-max-page) mx-auto",
  wide: "px-fluid-x max-w-(--layout-max-wide) mx-auto",
  narrow: "px-fluid-x max-w-(--layout-max-content) mx-auto",
  full: "p-0",
}

export const PageLayout = ({ children, className, variant = "default" }: PageLayoutProps) => {
  return (
    <Layout>
      <PageFadeIn>
        <div className={cn("w-full py-6 md:py-8", variants[variant], className)}>{children}</div>
      </PageFadeIn>
    </Layout>
  )
}
