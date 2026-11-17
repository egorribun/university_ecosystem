/**
 * useMapKeyboardShortcuts.ts — Keyboard shortcuts for the campus map page.
 *
 * Keys 1-9 select buildings, F toggles fullscreen, / focuses search,
 * ? opens the shortcuts overlay. All keys are ignored when focus is
 * inside an input, textarea, select, or contenteditable element.
 *
 * Wave 108 — keyboard navigation for map page.
 */

import { useEffect } from "react"
import { BUILDING_IDS, type BuildingId } from "@/data/campusBuildings"

interface MapKeyboardDeps {
  onSelectBuilding: (id: BuildingId) => void
  onToggleFullscreen: () => void
  onFocusSearch: () => void
  onToggleShortcuts: () => void
}

const INTERACTIVE_TAGS = new Set(["INPUT", "TEXTAREA", "SELECT"])

/**
 * Register global keyboard shortcuts for the campus map.
 *
 * @param deps  Callbacks for each shortcut action
 */
export function useMapKeyboardShortcuts(deps: MapKeyboardDeps): void {
  const { onSelectBuilding, onToggleFullscreen, onFocusSearch, onToggleShortcuts } = deps

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      // Preserve browser/OS chords (especially Find), IME, and controls that
      // already handled the event. Shift remains available for the ? shortcut.
      if (e.defaultPrevented || e.isComposing || e.ctrlKey || e.metaKey || e.altKey) return

      const target = e.target as HTMLElement | null
      if (!target) return

      // Skip when focus is inside an editable element
      if (INTERACTIVE_TAGS.has(target.tagName)) return
      // contenteditable is inherited; the nearest valid value owns this context.
      // A false island re-enables shortcuts, while an empty value enables editing.
      const editingHost = target.closest(
        '[contenteditable=""], [contenteditable="true" i], ' +
          '[contenteditable="plaintext-only" i], [contenteditable="false" i]'
      )
      if (editingHost && !editingHost.matches('[contenteditable="false" i]')) {
        return
      }

      // 1-9: select building by index
      const keyNum = parseInt(e.key, 10)
      if (keyNum >= 1 && keyNum <= 9) {
        const index = keyNum - 1
        const buildingId = BUILDING_IDS[index]!
        onSelectBuilding(buildingId)
        return
      }

      // F: toggle fullscreen (preventDefault avoids Firefox quick-find)
      if (e.key === "f" || e.key === "F") {
        e.preventDefault()
        onToggleFullscreen()
        return
      }

      // /: focus search bar
      if (e.key === "/" && !e.shiftKey) {
        e.preventDefault()
        onFocusSearch()
        return
      }

      // ?: open shortcuts overlay
      if (e.key === "?" || (e.shiftKey && e.key === "/")) {
        e.preventDefault()
        onToggleShortcuts()
      }
    }

    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [onSelectBuilding, onToggleFullscreen, onFocusSearch, onToggleShortcuts])
}
