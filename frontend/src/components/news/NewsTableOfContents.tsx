import { useCallback, useEffect, useRef, useState } from "react"
import { List as TocIcon } from "lucide-react"
import { useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"
import type { TocEntry } from "@/hooks/useArticleHeadings"
import useMediaQuery from "@/hooks/useMediaQuery"

interface NewsTableOfContentsProps {
  headings: TocEntry[]
}

export function NewsTableOfContents({ headings }: NewsTableOfContentsProps) {
  const { t } = useTranslation(["news"])
  const [activeId, setActiveId] = useState("")
  const [collapsed, setCollapsed] = useState(true)
  const observerRef = useRef<IntersectionObserver | null>(null)
  const isDesktop = useMediaQuery("(min-width: 1024px)")

  // Reset collapsed state when headings change (article navigation)
  useEffect(() => {
    setCollapsed(true)
  }, [headings])

  // On desktop, always show expanded
  const isExpanded = isDesktop || !collapsed

  /* ── IntersectionObserver to track active heading ── */
  useEffect(() => {
    if (headings.length === 0) return

    observerRef.current?.disconnect()

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActiveId(entry.target.id)
          }
        }
      },
      { rootMargin: "-80px 0px -70% 0px", threshold: 0 }
    )

    observerRef.current = observer

    // Observe each heading element by ID
    for (const heading of headings) {
      const el = document.getElementById(heading.id)
      if (el) observer.observe(el)
    }

    return () => observer.disconnect()
  }, [headings])

  const scrollToHeading = useCallback(
    (id: string) => {
      const el = document.getElementById(id)
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" })
        setActiveId(id)
        if (!isDesktop) setCollapsed(true)
      }
    },
    [isDesktop]
  )

  if (headings.length < 3) return null

  return (
    <nav
      className={cn(
        "news-toc rounded-xl border border-glass-border/(--opacity-soft) overflow-hidden transition-all duration-base",
        isDesktop ? "glass-layer-surface glass-noise" : "glass-layer-surface"
      )}
      aria-label={t("news:toc.label")}
    >
      {/* Header — always visible */}
      <button
        type="button"
        onClick={() => !isDesktop && setCollapsed(!collapsed)}
        className={cn(
          "flex w-full items-center gap-2 px-4 py-3 text-sm font-bold text-text-primary transition-colors",
          !isDesktop && "hover:bg-(--bg-surface)/(--opacity-hover)"
        )}
        aria-expanded={isExpanded}
        disabled={isDesktop}
      >
        <TocIcon size={16} className="text-brand shrink-0" />
        <span>{t("news:toc.title")}</span>
        <span className="ml-auto tabular-nums text-xs text-(--text-secondary)">
          {headings.length}
        </span>
        {!isDesktop && (
          <svg
            className={cn(
              "h-4 w-4 text-(--text-secondary) transition-transform duration-fast",
              isExpanded && "rotate-180"
            )}
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path d="M4 6l4 4 4-4" />
          </svg>
        )}
      </button>

      {/* Links */}
      {isExpanded && (
        <ul className="flex flex-col gap-0.5 px-2 pb-3">
          {headings.map((heading) => (
            <li key={heading.id}>
              <button
                type="button"
                onClick={() => scrollToHeading(heading.id)}
                className={cn(
                  "w-full text-left rounded-lg px-3 py-1.5 text-sm leading-snug transition-colors",
                  heading.level === 3 && "pl-6",
                  activeId === heading.id
                    ? "bg-brand/(--opacity-subtle) text-brand font-semibold"
                    : "text-(--text-secondary) hover:text-text-primary hover:bg-(--bg-surface)/(--opacity-hover)"
                )}
              >
                {heading.text}
              </button>
            </li>
          ))}
        </ul>
      )}
    </nav>
  )
}
