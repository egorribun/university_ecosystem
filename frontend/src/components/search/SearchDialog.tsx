/**
 * SearchDialog — Global Cmd+K search with glass morphism
 *
 * Features:
 * - Keyboard shortcut Cmd+K (Mac) / Ctrl+K (Windows)
 * - Debounced search with 200ms delay
 * - Results grouped by type (news, events)
 * - Keyboard navigation (Arrow keys + Enter)
 * - Recent searches in localStorage
 * - Glass morphism Layer 3 (floating)
 * - Accessible: role="dialog", aria-modal, focus trap
 *
 * Wave 38: AI-powered search foundation
 */

import { useState, useEffect, useRef, useCallback, useMemo, type KeyboardEvent } from "react"
import { useNavigate } from "@tanstack/react-router"
import { m, AnimatePresence } from "framer-motion"
import { Search, X, FileText, Calendar, ArrowRight, Clock } from "lucide-react"
import { useTranslation } from "react-i18next"
import { useQuery } from "@tanstack/react-query"
import api from "@/api/client"
import { cn } from "@/utils/cn"
import { useDebounced } from "@/hooks/useDebounced"

interface SearchResult {
  id: string
  type: "news" | "events"
  title: string
  summary: string
  score: number
  url: string
}

interface SearchResponse {
  query: string
  results: {
    news?: SearchResult[]
    events?: SearchResult[]
  }
}

const RECENT_SEARCHES_KEY = "ue:recent-searches"
const MAX_RECENT = 5

function getRecentSearches(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_SEARCHES_KEY)
    return raw ? (JSON.parse(raw) as string[]).slice(0, MAX_RECENT) : []
  } catch {
    return []
  }
}

function saveRecentSearch(query: string) {
  try {
    const recent = getRecentSearches().filter((s) => s !== query)
    recent.unshift(query)
    localStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(recent.slice(0, MAX_RECENT)))
  } catch {
    // RZ-31-03: Safari private browsing
  }
}

export function SearchDialog() {
  const { t } = useTranslation(["common"])
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const [activeIndex, setActiveIndex] = useState(-1)
  const inputRef = useRef<HTMLInputElement>(null)
  const resultsRef = useRef<HTMLDivElement>(null)
  const isMac = useMemo(
    () => typeof navigator !== "undefined" && /Mac/i.test(navigator.platform),
    []
  )

  const debouncedQuery = useDebounced(query, "search")

  // Global Cmd+K / Ctrl+K shortcut
  useEffect(() => {
    const handler = (e: globalThis.KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault()
        setOpen((prev) => !prev)
      }
      if (e.key === "Escape" && open) {
        setOpen(false)
      }
    }
    document.addEventListener("keydown", handler)
    return () => document.removeEventListener("keydown", handler)
  }, [open])

  // Focus input when opened
  useEffect(() => {
    if (open) {
      requestAnimationFrame(() => inputRef.current?.focus())
    } else {
      setQuery("")
      setActiveIndex(-1)
    }
  }, [open])

  // Search query
  const { data, isLoading } = useQuery<SearchResponse>({
    queryKey: ["search", debouncedQuery],
    queryFn: async () => {
      const res = await api.get<SearchResponse>("/search", {
        params: { q: debouncedQuery, type: "all", limit: 8 },
      })
      return res.data
    },
    enabled: open && debouncedQuery.length >= 2,
    staleTime: 30_000,
  })

  const allResults: SearchResult[] = [
    ...(data?.results.news ?? []),
    ...(data?.results.events ?? []),
  ].sort((a, b) => b.score - a.score)

  const handleSelect = useCallback(
    (result: SearchResult) => {
      saveRecentSearch(query)
      setOpen(false)
      navigate({ to: result.url })
    },
    [navigate, query]
  )

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "ArrowDown") {
        e.preventDefault()
        setActiveIndex((prev) => Math.min(prev + 1, allResults.length - 1))
      } else if (e.key === "ArrowUp") {
        e.preventDefault()
        setActiveIndex((prev) => Math.max(prev - 1, -1))
      } else if (e.key === "Enter" && activeIndex >= 0 && allResults[activeIndex]) {
        e.preventDefault()
        handleSelect(allResults[activeIndex])
      }
    },
    [activeIndex, allResults, handleSelect]
  )

  // Scroll active item into view
  useEffect(() => {
    if (activeIndex >= 0) {
      const items = resultsRef.current?.querySelectorAll("[data-search-item]")
      items?.[activeIndex]?.scrollIntoView({ block: "nearest" })
    }
  }, [activeIndex])

  const recentSearches = getRecentSearches()
  const showRecent = !query && recentSearches.length > 0
  const showResults = debouncedQuery.length >= 2
  const TypeIcon = { news: FileText, events: Calendar } as const

  if (!open) return null

  return (
    <AnimatePresence>
      <m.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-modal flex items-start justify-center pt-[15vh] bg-overlay/(--opacity-strong) backdrop-blur-md"
        onClick={() => setOpen(false)}
        role="presentation"
      >
        <m.div
          initial={{ opacity: 0, scale: 0.95, y: -20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: -20 }}
          transition={{ type: "spring" as const, stiffness: 400, damping: 30 }}
          className="glass-layer-floating w-full max-w-[36rem] rounded-2xl overflow-hidden"
          onClick={(e) => e.stopPropagation()}
          role="dialog"
          aria-modal="true"
          aria-label={t("common:search.title")}
        >
          {/* Search Input */}
          <div className="flex items-center gap-3 border-b border-glass-border p-4">
            <Search className="h-5 w-5 shrink-0 text-(--text-tertiary)" aria-hidden="true" />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value)
                setActiveIndex(-1)
              }}
              onKeyDown={handleKeyDown}
              placeholder={t("common:search.placeholder")}
              className="flex-1 bg-transparent text-base font-medium text-text-primary placeholder:text-text-tertiary outline-none"
              aria-label={t("common:search.inputLabel")}
            />
            {query && (
              <button
                type="button"
                onClick={() => setQuery("")}
                className="p-1 rounded-md hover:bg-(--bg-surface-hover) transition-colors"
                aria-label={t("common:search.clear")}
              >
                <X className="h-4 w-4 text-(--text-tertiary)" />
              </button>
            )}
            <kbd className="hidden sm:flex items-center gap-0.5 rounded-md border border-glass-border bg-glass px-1.5 py-0.5 text-xs font-medium text-(--text-tertiary)">
              Esc
            </kbd>
          </div>

          {/* Results */}
          <div ref={resultsRef} className="max-h-80 overflow-y-auto custom-scrollbar">
            {/* Recent Searches */}
            {showRecent && (
              <div className="p-2">
                <p className="px-3 py-1.5 text-xs font-bold uppercase tracking-widest text-(--text-tertiary)">
                  {t("common:search.recent")}
                </p>
                {recentSearches.map((recent) => (
                  <button
                    key={recent}
                    type="button"
                    onClick={() => setQuery(recent)}
                    className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-text-secondary hover:bg-(--bg-surface-hover) transition-colors"
                  >
                    <Clock className="h-4 w-4 shrink-0" aria-hidden="true" />
                    {recent}
                  </button>
                ))}
              </div>
            )}

            {/* Loading */}
            {isLoading && showResults && (
              <div className="flex items-center justify-center py-8">
                <div className="h-5 w-5 animate-spin rounded-full border-2 border-(--text-tertiary) border-t-brand" />
              </div>
            )}

            {/* Search Results */}
            {!isLoading && showResults && allResults.length > 0 && (
              <div className="p-2">
                {allResults.map((result, idx) => {
                  const Icon = TypeIcon[result.type] ?? FileText
                  return (
                    <button
                      key={`${result.type}-${result.id}`}
                      type="button"
                      data-search-item
                      onClick={() => handleSelect(result)}
                      className={cn(
                        "flex w-full items-center gap-3 rounded-lg px-3 py-3 text-left transition-colors",
                        idx === activeIndex
                          ? "bg-brand/(--opacity-subtle) text-brand"
                          : "text-text-primary hover:bg-(--bg-surface-hover)"
                      )}
                    >
                      <div
                        className={cn(
                          "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
                          result.type === "news"
                            ? "bg-brand/(--opacity-subtle) text-brand"
                            : "bg-success-bg text-success-text"
                        )}
                      >
                        <Icon className="h-4 w-4" aria-hidden="true" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-semibold">{result.title}</p>
                        {result.summary && (
                          <p className="truncate text-xs text-(--text-tertiary)">
                            {result.summary}
                          </p>
                        )}
                      </div>
                      <ArrowRight
                        className={cn(
                          "h-4 w-4 shrink-0 transition-opacity",
                          idx === activeIndex ? "opacity-100" : "opacity-0"
                        )}
                        aria-hidden="true"
                      />
                    </button>
                  )
                })}
              </div>
            )}

            {/* No Results */}
            {!isLoading && showResults && allResults.length === 0 && (
              <div className="py-8 text-center">
                <p className="text-sm font-medium text-(--text-tertiary)">
                  {t("common:search.noResults")}
                </p>
              </div>
            )}

            {/* Empty State */}
            {!showRecent && !showResults && (
              <div className="py-8 text-center">
                <p className="text-sm font-medium text-(--text-tertiary)">
                  {t("common:search.hint")}
                </p>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between border-t border-glass-border px-4 py-2 text-xs text-(--text-tertiary)">
            <div className="flex items-center gap-2">
              <kbd className="rounded border border-glass-border px-1.5 py-0.5 font-mono">↑↓</kbd>
              <span>{t("common:search.navigate")}</span>
              <kbd className="rounded border border-glass-border px-1.5 py-0.5 font-mono">↵</kbd>
              <span>{t("common:search.select")}</span>
            </div>
            <span className="hidden sm:inline">
              <kbd className="rounded border border-glass-border px-1.5 py-0.5 font-mono">
                {isMac ? "⌘" : "Ctrl"}+K
              </kbd>
            </span>
          </div>
        </m.div>
      </m.div>
    </AnimatePresence>
  )
}
