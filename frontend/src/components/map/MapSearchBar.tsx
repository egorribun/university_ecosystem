import {
  useState,
  useMemo,
  useCallback,
  useRef,
  useId,
  useEffect,
  useImperativeHandle,
  type KeyboardEvent,
} from "react"
import { useTranslation } from "react-i18next"
import { Search, X } from "lucide-react"
import type { CampusBuilding, BuildingId } from "@/data/campusBuildings"

type SearchResult =
  | {
      type: "building"
      buildingLetter: BuildingId
      label: string
      sublabel?: string
    }
  | {
      type: "room"
      buildingLetter: BuildingId
      label: string
      sublabel?: string
      roomId: string
      floor: number
    }

type SelectionResult = SearchResult | { type: "none" }

const NO_SELECTION: SelectionResult = { type: "none" }

/**
 * Dispatch a selected result to the matching consumer.  A stale keyboard or
 * pointer event may arrive without a result while the dropdown is closing;
 * treating that input as a no-op keeps the selection boundary total.
 */
export function applySearchSelection(
  result: SelectionResult | undefined,
  onSelectBuilding: (letter: BuildingId) => void,
  onSelectRoom: (letter: BuildingId, floor: number, roomId: string) => void,
  onSelectionApplied?: () => void
): boolean {
  const selected = result ?? NO_SELECTION
  switch (selected.type) {
    case "building":
      onSelectBuilding(selected.buildingLetter)
      break
    case "room":
      onSelectRoom(selected.buildingLetter, selected.floor, selected.roomId)
      break
    default:
      return false
  }
  onSelectionApplied?.()
  return true
}

/** Keep transient focus operations total when a route transition clears the ref. */
export function blurSearchInput(input: HTMLInputElement | null): void {
  if (input) input.blur()
}

/** Keep the clear-button focus operation total when its input has unmounted. */
export function focusSearchInput(input: HTMLInputElement | null): void {
  if (input) input.focus()
}

interface MapSearchBarProps {
  buildings: CampusBuilding[]
  onSelectBuilding: (letter: BuildingId) => void
  onSelectRoom: (letter: BuildingId, floor: number, roomId: string) => void
  /** External ref for keyboard shortcut "/" focus (Wave 108) */
  searchInputRef?: React.RefObject<HTMLInputElement | null>
}

/**
 * MapSearchBar — fuzzy autocomplete over buildings + rooms.
 * role="combobox" + aria-expanded + aria-activedescendant.
 */
export function MapSearchBar({
  buildings,
  onSelectBuilding,
  onSelectRoom,
  searchInputRef,
}: MapSearchBarProps) {
  const { t } = useTranslation("map")
  const baseId = useId()
  const listboxId = `${baseId}-listbox`
  const inputRef = useRef<HTMLInputElement>(null)

  const [query, setQuery] = useState("")
  const [isOpen, setIsOpen] = useState(() => query.length > 0)
  // null represents "no active option" without relying on a magic sentinel.
  const [activeIdx, setActiveIdx] = useState<number | null>(null)

  // Tracks the blur→close timeout so it can be cancelled on unmount or explicit
  // close events, preventing state updates into a torn-down environment.
  const blurTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // A successful keyboard/click selection deliberately blurs the input. That
  // blur must not schedule a delayed close which can race with an immediate
  // second search and swallow its Escape/Enter key handling.
  const skipNextBlurCloseRef = useRef(false)

  useEffect(() => {
    return () => {
      if (blurTimeoutRef.current !== null) {
        clearTimeout(blurTimeoutRef.current)
      }
    }
  }, [])

  const results = useMemo((): SearchResult[] => {
    const q = query.trim().toLowerCase()
    if (!q) return []

    const items: SearchResult[] = []

    for (const bldg of buildings) {
      // Match building name
      if (bldg.name.toLowerCase().includes(q) || bldg.letter.toLowerCase() === q) {
        items.push({
          type: "building",
          buildingLetter: bldg.letter,
          label: bldg.name,
          sublabel: t("tooltip.floors", { count: bldg.floorCount }),
        })
      }

      // Match rooms
      for (const floor of bldg.floors) {
        for (const room of floor.rooms) {
          const roomName = room.name?.toLowerCase() ?? ""
          if (room.id.toLowerCase().includes(q) || roomName.includes(q)) {
            items.push({
              type: "room",
              buildingLetter: bldg.letter,
              label: room.id,
              sublabel: room.name,
              roomId: room.id,
              floor: floor.floor,
            })
          }
        }
      }
    }

    return items.slice(0, 12)
  }, [query, buildings, t])

  const handleSelect = useCallback(
    (result: SelectionResult | undefined) => {
      applySearchSelection(result, onSelectBuilding, onSelectRoom, () => {
        // Cancel any pending blur→close timer so it doesn't race with this explicit close.
        if (blurTimeoutRef.current !== null) {
          clearTimeout(blurTimeoutRef.current)
          blurTimeoutRef.current = null
        }
        setQuery("")
        setActiveIdx(null)
        skipNextBlurCloseRef.current = true
        blurSearchInput(inputRef.current)
      })
    },
    [onSelectBuilding, onSelectRoom]
  )

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>) => {
      if (!isOpen || results.length === 0) return

      switch (e.key) {
        case "ArrowDown":
          e.preventDefault()
          setActiveIdx((prev) => Math.min((prev ?? -1) + 1, results.length - 1))
          break
        case "ArrowUp":
          e.preventDefault()
          setActiveIdx((prev) => Math.max((prev ?? 0) - 1, 0))
          break
        case "Enter": {
          e.preventDefault()
          // Slicing at the active index yields either exactly one valid result
          // or an empty iterable. It keeps Enter a total operation even when
          // focus/async updates leave no active option.
          const selectedIndex = activeIdx ?? results.length
          for (const result of results.slice(selectedIndex, selectedIndex + 1)) {
            handleSelect(result)
          }
          break
        }
        case "Escape":
          e.preventDefault()
          setQuery("")
          setActiveIdx(null)
          break
      }
    },
    [isOpen, results, activeIdx, handleSelect]
  )

  // useImperativeHandle runs after the input is committed, so the local DOM
  // ref is populated even though it is nullable during render.
  const imperativeHandleIdentity = useMemo(() => searchInputRef, [searchInputRef])
  useImperativeHandle(searchInputRef, () => {
    // Keep the handle tied to the current external ref identity when a
    // parent swaps refs during a route transition.
    void imperativeHandleIdentity
    return inputRef.current!
  }, [imperativeHandleIdentity])

  // Group results
  const buildingResults = results.filter((r) => r.type === "building")
  const roomResults = results.filter((r) => r.type === "room")

  return (
    <div className="relative">
      <div className="map-card-matte flex items-center gap-2 px-3 py-2 focus-within:ring-2 focus-within:ring-[var(--color-teal-500)]/40 transition-shadow">
        <Search className="h-4 w-4 text-[var(--text-tertiary)] shrink-0" />
        <input
          ref={inputRef}
          type="text"
          role="combobox"
          aria-expanded={isOpen && results.length > 0}
          aria-controls={listboxId}
          aria-activedescendant={activeIdx !== null ? `${baseId}-opt-${activeIdx}` : undefined}
          aria-label={t("search.ariaLabel")}
          placeholder={t("search.placeholder")}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setIsOpen(true)
            setActiveIdx(null)
          }}
          onFocus={() => results.length > 0 && setIsOpen(true)}
          onBlur={() => {
            if (skipNextBlurCloseRef.current) {
              skipNextBlurCloseRef.current = false
              return
            }
            blurTimeoutRef.current = setTimeout(() => setIsOpen(false), 200)
          }}
          onKeyDown={handleKeyDown}
          className="flex-1 bg-transparent text-sm font-medium text-text-primary placeholder:text-[var(--text-tertiary)] outline-none"
        />
        {query && (
          <button
            type="button"
            onClick={() => {
              // Cancel the blur timer that fires when the clear button receives focus.
              if (blurTimeoutRef.current !== null) {
                clearTimeout(blurTimeoutRef.current)
                blurTimeoutRef.current = null
              }
              setQuery("")
              setActiveIdx(null)
              focusSearchInput(inputRef.current)
            }}
            className="min-h-[44px] min-w-[44px] flex items-center justify-center rounded-full hover:bg-[var(--bg-surface-hover)]"
            aria-label={t("search.clear")}
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Dropdown */}
      {isOpen && results.length > 0 && (
        <div
          id={listboxId}
          role="listbox"
          className="absolute top-full left-0 right-0 mt-1 z-20 map-card-matte max-h-[min(16rem,calc(100dvh-200px))] overflow-y-auto"
        >
          {buildingResults.length > 0 && (
            <div className="px-3 pt-2 pb-1">
              <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-tertiary)]">
                {t("search.groupBuildings")}
              </p>
            </div>
          )}
          {buildingResults.map((r, i) => {
            const globalIdx = i
            return (
              <button
                key={r.buildingLetter}
                id={`${baseId}-opt-${globalIdx}`}
                role="option"
                aria-selected={activeIdx === globalIdx}
                type="button"
                onClick={() => handleSelect(r)}
                onPointerEnter={() => setActiveIdx(globalIdx)}
                className="w-full flex items-center gap-3 px-3 py-2 text-left text-sm transition-colors hover:bg-[var(--bg-surface-hover)] focus-visible:ring-2 focus-visible:ring-[var(--map-accent-icon)] focus-visible:outline-none"
                style={
                  activeIdx === globalIdx
                    ? { backgroundColor: "var(--bg-surface-hover)" }
                    : undefined
                }
              >
                <span className="font-bold">{r.label}</span>
                {r.sublabel && (
                  <span className="text-xs text-[var(--text-tertiary)]">{r.sublabel}</span>
                )}
              </button>
            )
          })}

          {roomResults.length > 0 && (
            <div className="px-3 pt-2 pb-1">
              <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-tertiary)]">
                {t("search.groupRooms")}
              </p>
            </div>
          )}
          {roomResults.map((r, i) => {
            const globalIdx = buildingResults.length + i
            return (
              <button
                key={r.roomId}
                id={`${baseId}-opt-${globalIdx}`}
                role="option"
                aria-selected={activeIdx === globalIdx}
                type="button"
                onClick={() => handleSelect(r)}
                onPointerEnter={() => setActiveIdx(globalIdx)}
                className="w-full flex items-center gap-3 px-3 py-2 text-left text-sm transition-colors hover:bg-[var(--bg-surface-hover)] focus-visible:ring-2 focus-visible:ring-[var(--map-accent-icon)] focus-visible:outline-none"
                style={
                  activeIdx === globalIdx
                    ? { backgroundColor: "var(--bg-surface-hover)" }
                    : undefined
                }
              >
                <span className="font-bold">{r.label}</span>
                {r.sublabel && (
                  <span className="text-xs text-[var(--text-tertiary)]">{r.sublabel}</span>
                )}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
