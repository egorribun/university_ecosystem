import { useEffect, useCallback, useRef, useState } from "react"

interface UseScheduleKeyboardNavOptions {
  /** Number of visible columns (days) */
  colCount: number
  /** Number of visible rows (time slots) */
  rowCount: number
  /** Index of today's column (-1 if no today) */
  todayColIdx: number
  /** Callback when a cell is selected */
  onSelect?: (row: number, col: number) => void
  /** Callback to open lesson details */
  onOpen?: () => void
  /** Callback to edit lesson */
  onEdit?: () => void
  /** Callback to delete lesson */
  onDelete?: () => void
  /** Callback to toggle shortcuts overlay */
  onToggleShortcuts?: () => void
  /** Whether keyboard nav is enabled */
  enabled?: boolean
}

interface CellPosition {
  row: number
  col: number
}

export function useScheduleKeyboardNav({
  colCount,
  rowCount,
  todayColIdx,
  onSelect,
  onOpen,
  onEdit,
  onDelete,
  onToggleShortcuts,
  enabled = true,
}: UseScheduleKeyboardNavOptions) {
  const [activeCell, setActiveCell] = useState<CellPosition | null>(null)
  const gridRef = useRef<HTMLDivElement | null>(null)

  const moveTo = useCallback(
    (row: number, col: number) => {
      const clamped = {
        row: Math.max(0, Math.min(row, rowCount - 1)),
        col: Math.max(0, Math.min(col, colCount - 1)),
      }
      setActiveCell(clamped)
      onSelect?.(clamped.row, clamped.col)

      // Focus the cell element
      const cellId = `sched-cell-${clamped.row}-${clamped.col}`
      const el = document.getElementById(cellId)
      if (el) {
        el.focus({ preventScroll: false })
        el.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" })
      }
    },
    [colCount, rowCount, onSelect],
  )

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!enabled || rowCount === 0 || colCount === 0) return

      // Skip if user is typing in an input/textarea
      const target = e.target as HTMLElement
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT") {
        return
      }

      const pos = activeCell ?? { row: 0, col: 0 }

      switch (e.key) {
        case "ArrowRight":
          e.preventDefault()
          moveTo(pos.row, pos.col + 1)
          break
        case "ArrowLeft":
          e.preventDefault()
          moveTo(pos.row, pos.col - 1)
          break
        case "ArrowDown":
          e.preventDefault()
          moveTo(pos.row + 1, pos.col)
          break
        case "ArrowUp":
          e.preventDefault()
          moveTo(pos.row - 1, pos.col)
          break
        case "Enter":
          e.preventDefault()
          onOpen?.()
          break
        case "e":
        case "E":
          if (!e.ctrlKey && !e.metaKey) {
            e.preventDefault()
            onEdit?.()
          }
          break
        case "Delete":
        case "Backspace":
          if (!e.ctrlKey && !e.metaKey) {
            e.preventDefault()
            onDelete?.()
          }
          break
        case "t":
        case "T":
          if (!e.ctrlKey && !e.metaKey && todayColIdx >= 0) {
            e.preventDefault()
            moveTo(pos.row, todayColIdx)
          }
          break
        case "?":
          e.preventDefault()
          onToggleShortcuts?.()
          break
        case "Escape":
          e.preventDefault()
          setActiveCell(null)
          break
      }
    },
    [enabled, activeCell, rowCount, colCount, moveTo, todayColIdx, onOpen, onEdit, onDelete, onToggleShortcuts],
  )

  useEffect(() => {
    if (!enabled) return
    document.addEventListener("keydown", handleKeyDown)
    return () => document.removeEventListener("keydown", handleKeyDown)
  }, [enabled, handleKeyDown])

  return {
    activeCell,
    setActiveCell,
    gridRef,
    clearSelection: () => setActiveCell(null),
  }
}
