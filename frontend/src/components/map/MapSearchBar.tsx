import { useState, useMemo, useCallback, useRef, useId, type KeyboardEvent } from "react"
import { useTranslation } from "react-i18next"
import { Search, X } from "lucide-react"
import type { CampusBuilding, BuildingLetter } from "@/data/campusBuildings"

interface SearchResult {
  type: "building" | "room"
  buildingLetter: BuildingLetter
  label: string
  sublabel?: string
  roomId?: string
  floor?: number
}

interface MapSearchBarProps {
  buildings: CampusBuilding[]
  onSelectBuilding: (letter: BuildingLetter) => void
  onSelectRoom: (letter: BuildingLetter, floor: number, roomId: string) => void
}

/**
 * MapSearchBar — fuzzy autocomplete over buildings + rooms.
 * role="combobox" + aria-expanded + aria-activedescendant.
 */
export function MapSearchBar({ buildings, onSelectBuilding, onSelectRoom }: MapSearchBarProps) {
  const { t } = useTranslation("map")
  const baseId = useId()
  const listboxId = `${baseId}-listbox`
  const inputRef = useRef<HTMLInputElement>(null)

  const [query, setQuery] = useState("")
  const [isOpen, setIsOpen] = useState(false)
  const [activeIdx, setActiveIdx] = useState(-1)

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
    (result: SearchResult) => {
      if (result.type === "building") {
        onSelectBuilding(result.buildingLetter)
      } else if (result.roomId && result.floor) {
        onSelectRoom(result.buildingLetter, result.floor, result.roomId)
      }
      setQuery("")
      setIsOpen(false)
      inputRef.current?.blur()
    },
    [onSelectBuilding, onSelectRoom],
  )

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>) => {
      if (!isOpen || results.length === 0) return

      switch (e.key) {
        case "ArrowDown":
          e.preventDefault()
          setActiveIdx((prev) => Math.min(prev + 1, results.length - 1))
          break
        case "ArrowUp":
          e.preventDefault()
          setActiveIdx((prev) => Math.max(prev - 1, 0))
          break
        case "Enter":
          e.preventDefault()
          if (activeIdx >= 0 && activeIdx < results.length) {
            handleSelect(results[activeIdx])
          }
          break
        case "Escape":
          e.preventDefault()
          setIsOpen(false)
          setQuery("")
          break
      }
    },
    [isOpen, results, activeIdx, handleSelect],
  )

  // Group results
  const buildingResults = results.filter((r) => r.type === "building")
  const roomResults = results.filter((r) => r.type === "room")

  return (
    <div className="relative">
      <div className="map-card-matte flex items-center gap-2 px-3 py-2">
        <Search className="h-4 w-4 text-[var(--text-tertiary)] shrink-0" />
        <input
          ref={inputRef}
          type="text"
          role="combobox"
          aria-expanded={isOpen && results.length > 0}
          aria-controls={listboxId}
          aria-activedescendant={activeIdx >= 0 ? `${baseId}-opt-${activeIdx}` : undefined}
          aria-label={t("search.ariaLabel")}
          placeholder={t("search.placeholder")}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setIsOpen(true)
            setActiveIdx(-1)
          }}
          onFocus={() => query.trim() && setIsOpen(true)}
          onBlur={() => setTimeout(() => setIsOpen(false), 200)}
          onKeyDown={handleKeyDown}
          className="flex-1 bg-transparent text-sm font-medium text-text-primary placeholder:text-[var(--text-tertiary)] outline-none"
        />
        {query && (
          <button
            type="button"
            onClick={() => {
              setQuery("")
              setIsOpen(false)
              inputRef.current?.focus()
            }}
            className="h-5 w-5 flex items-center justify-center rounded-full hover:bg-[var(--bg-surface-hover)]"
            aria-label="Clear"
          >
            <X className="h-3 w-3" />
          </button>
        )}
      </div>

      {/* Dropdown */}
      {isOpen && results.length > 0 && (
        <div
          id={listboxId}
          role="listbox"
          className="absolute top-full left-0 right-0 mt-1 z-20 map-card-matte max-h-64 overflow-y-auto"
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
                key={`b-${r.buildingLetter}`}
                id={`${baseId}-opt-${globalIdx}`}
                role="option"
                aria-selected={activeIdx === globalIdx}
                type="button"
                onClick={() => handleSelect(r)}
                onPointerEnter={() => setActiveIdx(globalIdx)}
                className="w-full flex items-center gap-3 px-3 py-2 text-left text-sm transition-colors hover:bg-[var(--bg-surface-hover)]"
                style={activeIdx === globalIdx ? { backgroundColor: "var(--bg-surface-hover)" } : undefined}
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
                key={`r-${r.roomId}`}
                id={`${baseId}-opt-${globalIdx}`}
                role="option"
                aria-selected={activeIdx === globalIdx}
                type="button"
                onClick={() => handleSelect(r)}
                onPointerEnter={() => setActiveIdx(globalIdx)}
                className="w-full flex items-center gap-3 px-3 py-2 text-left text-sm transition-colors hover:bg-[var(--bg-surface-hover)]"
                style={activeIdx === globalIdx ? { backgroundColor: "var(--bg-surface-hover)" } : undefined}
              >
                <span className="font-bold">{r.label}</span>
                {r.sublabel && (
                  <span className="text-xs text-[var(--text-tertiary)]">{r.sublabel}</span>
                )}
              </button>
            )
          })}

          {results.length === 0 && (
            <p className="px-3 py-4 text-sm text-center text-[var(--text-tertiary)]">
              {t("search.noResults")}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
