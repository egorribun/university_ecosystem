import { useCallback, useEffect, useRef, useState } from "react"
import { useNavigate } from "@tanstack/react-router"

interface NewsItem {
  id: string
}

/**
 * Vim-style J/K keyboard navigation for news card grid.
 * J = next, K = previous, Enter = open article.
 * Disabled when search input or dialog is focused.
 */
export function useNewsKeyboardNav(items: NewsItem[]) {
  const [activeIndex, setActiveIndex] = useState(-1)
  const navigate = useNavigate()
  const cardRefs = useRef<Map<number, HTMLElement>>(new Map())

  const registerRef = useCallback((index: number, el: HTMLElement | null) => {
    if (el) {
      cardRefs.current.set(index, el)
    } else {
      cardRefs.current.delete(index)
    }
  }, [])

  const scrollToCard = useCallback((index: number) => {
    const el = cardRefs.current.get(index)
    el?.scrollIntoView({ behavior: "smooth", block: "center" })
  }, [])

  useEffect(() => {
    if (items.length === 0) return

    function handleKeyDown(e: KeyboardEvent) {
      // Skip if focused in input, textarea, dialog, or contenteditable
      const tag = (e.target as HTMLElement).tagName
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return
      if ((e.target as HTMLElement).closest("[role='dialog']")) return
      if ((e.target as HTMLElement).isContentEditable) return

      switch (e.key) {
        case "j":
        case "J": {
          e.preventDefault()
          setActiveIndex((prev) => {
            const next = Math.min(prev + 1, items.length - 1)
            scrollToCard(next)
            return next
          })
          break
        }
        case "k":
        case "K": {
          e.preventDefault()
          setActiveIndex((prev) => {
            const next = Math.max(prev - 1, 0)
            scrollToCard(next)
            return next
          })
          break
        }
        case "Enter": {
          if (activeIndex >= 0 && activeIndex < items.length) {
            const item = items[activeIndex]
            if (item) {
              e.preventDefault()
              void navigate({ to: "/news/$id", params: { id: item.id } })
            }
          }
          break
        }
        case "Escape": {
          setActiveIndex(-1)
          break
        }
      }
    }

    document.addEventListener("keydown", handleKeyDown)
    return () => document.removeEventListener("keydown", handleKeyDown)
  }, [items, activeIndex, navigate, scrollToCard])

  // Reset when items change (filter/search)
  useEffect(() => { setActiveIndex(-1) }, [items])

  return { activeIndex, registerRef } as const
}
