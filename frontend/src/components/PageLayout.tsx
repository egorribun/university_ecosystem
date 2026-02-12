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
  default: "px-4 sm:px-8 md:px-12 lg:px-16",
  wide: "px-2 md:px-4",
  narrow: "px-4 sm:px-6 md:px-8 max-w-4xl mx-auto",
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
