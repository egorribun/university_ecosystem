import { ReactNode } from "react"
import Layout from "./Layout"
import PageFadeIn from "./PageFadeIn"
import { SEO, SEOProps } from "./SEO"
import { cn } from "@/utils/cn"

type PageLayoutVariant = "default" | "wide" | "narrow" | "full"

interface PageLayoutProps {
  children: ReactNode
  className?: string
  variant?: PageLayoutVariant
  seo?: SEOProps
}

const variants: Record<PageLayoutVariant, string> = {
  default: "px-fluid-x max-w-(--layout-max-page) mx-auto",
  wide: "px-fluid-x max-w-(--layout-max-wide) mx-auto",
  narrow: "px-fluid-x max-w-(--layout-max-content) mx-auto",
  full: "p-0",
}

export const PageLayout = ({ children, className, variant = "default", seo }: PageLayoutProps) => {
  return (
    <Layout>
      {seo && <SEO {...seo} />}
      <PageFadeIn>
        <div className={cn("w-full py-(--fluid-py)", variants[variant], className)}>{children}</div>
      </PageFadeIn>
    </Layout>
  )
}
