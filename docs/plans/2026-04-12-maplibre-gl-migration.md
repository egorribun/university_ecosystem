# Leaflet → MapLibre GL Migration Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace Leaflet (raster tiles, flat 2D) with MapLibre GL (WebGL vector tiles, 3D fill-extrusion buildings, native dark theme, pitch/bearing controls) in the campus map "Map" mode.

**Architecture:** `react-map-gl/maplibre` provides React components (`<Map>`, `<Marker>`, `<Popup>`, `<Source>`, `<Layer>`) that wrap `maplibre-gl`. OpenFreeMap supplies free vector tiles with building height data for 3D extrusion. All data layers (campusBuildings, campusPOI, useOverpassPOI) remain unchanged — only the rendering layer swaps. Lazy loading via `React.lazy()` preserved.

**Tech Stack:** maplibre-gl, react-map-gl/maplibre, OpenFreeMap vector tiles, fill-extrusion layer.

---

## Task 1: Swap Dependencies

**Files:**
- Modify: `frontend/package.json`

**Step 1: Uninstall Leaflet packages**

```bash
cd frontend
npm uninstall leaflet react-leaflet
npm uninstall -D @types/leaflet
```

**Step 2: Install MapLibre GL + react-map-gl**

```bash
npm install maplibre-gl react-map-gl
```

**Step 3: Verify installation**

```bash
node -e "require('maplibre-gl'); console.log('maplibre-gl OK')"
node -e "require('react-map-gl'); console.log('react-map-gl OK')"
```

Expected: both print OK with no errors.

**Step 4: Commit**

```bash
git add package.json package-lock.json
git commit -m "chore: swap leaflet → maplibre-gl + react-map-gl"
```

---

## Task 2: Rewrite BuildingMarker.tsx

Replace `L.divIcon` HTML string markers with pure JSX `<Marker>` + `<Popup>` from react-map-gl.

**Files:**
- Rewrite: `frontend/src/components/map/BuildingMarker.tsx`

**Step 1: Rewrite the component**

Replace the entire file. Key changes:
- Remove: `import L from "leaflet"`, `import { Marker, Popup, Tooltip } from "react-leaflet"`
- Add: `import { Marker, Popup } from "react-map-gl/maplibre"`
- Remove: `createBuildingIcon()` function (L.divIcon with innerHTML)
- Add: JSX children inside `<Marker>` (a styled `<div>` with the building letter)
- Change: `position={building.geoCoords}` → `longitude={building.geoCoords[1]} latitude={building.geoCoords[0]}`
  - **CRITICAL:** Leaflet uses `[lat, lng]`, MapLibre uses `longitude, latitude` as separate props.
  - `campusBuildings.ts` stores `geoCoords: [lat, lng]` → index 0 is lat, index 1 is lng
- Change: `eventHandlers={{ click: ... }}` → `onClick` prop on wrapper div (Marker has no onClick in react-map-gl)
- Replace: `<Tooltip>` (no equivalent in react-map-gl) → remove, keep popup only
- Replace: `<Popup>` → `<Popup>` from react-map-gl with `anchor="bottom"` + `offset={25}` + `closeButton={false}` + `closeOnClick={false}`

**Full replacement code:**

```tsx
import { useMemo, useState } from "react"
import { Marker, Popup } from "react-map-gl/maplibre"
import { useTranslation } from "react-i18next"
import type { CampusBuilding, BuildingLetter } from "@/data/campusBuildings"

interface BuildingMarkerProps {
  building: CampusBuilding
  isSelected: boolean
  isHighlighted: boolean
  onClick: (letter: BuildingLetter) => void
}

export function BuildingMarker({ building, isSelected, isHighlighted, onClick }: BuildingMarkerProps) {
  const { t } = useTranslation("map")
  const [showPopup, setShowPopup] = useState(false)

  const isActive = isSelected || isHighlighted
  const size = isActive ? 44 : 36
  const fontSize = isActive ? 18 : 15
  const borderWidth = isActive ? 3 : 2

  const roomCount = useMemo(
    () => building.floors.reduce((sum, f) => sum + f.rooms.length, 0),
    [building.floors],
  )

  return (
    <>
      <Marker
        longitude={building.geoCoords[1]}
        latitude={building.geoCoords[0]}
        anchor="center"
        onClick={(e) => {
          e.originalEvent.stopPropagation()
          onClick(building.letter)
          setShowPopup(true)
        }}
      >
        <div
          role="button"
          tabIndex={0}
          aria-label={t("a11y.buildingSelected", {
            name: building.name,
            floors: building.floorCount,
            rooms: roomCount,
          })}
          className="map-building-marker-3d"
          style={{
            width: size,
            height: size,
            background: building.colorHex,
            border: `${borderWidth}px solid white`,
            borderRadius: "50%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "white",
            fontWeight: 900,
            fontSize,
            boxShadow: `0 2px 8px rgba(0,0,0,0.3)${isActive ? `, 0 0 0 4px ${building.colorHex}40` : ""}`,
            cursor: "pointer",
            fontFamily: "var(--font-ui), Inter, system-ui, sans-serif",
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault()
              onClick(building.letter)
              setShowPopup(true)
            }
          }}
        >
          {building.letter}
        </div>
      </Marker>

      {showPopup && (
        <Popup
          longitude={building.geoCoords[1]}
          latitude={building.geoCoords[0]}
          anchor="bottom"
          offset={25}
          closeButton={true}
          closeOnClick={false}
          onClose={() => setShowPopup(false)}
          className="map-building-popup"
        >
          <div className="map-popup-content">
            <div className="flex items-center gap-2 mb-1">
              <span
                className="inline-flex items-center justify-center w-7 h-7 rounded-full text-white font-black text-sm"
                style={{ backgroundColor: building.colorHex }}
              >
                {building.letter}
              </span>
              <span className="font-bold text-sm">{building.name}</span>
            </div>
            <p className="text-xs opacity-70 mb-1">{building.structureId}</p>
            {building.description && (
              <p className="text-xs opacity-80 line-clamp-2">{building.description}</p>
            )}
            <div className="text-xs opacity-60 mt-1">
              {t("tooltip.floors", { count: building.floorCount })}
            </div>
          </div>
        </Popup>
      )}
    </>
  )
}
```

**Step 2: Verify TypeScript compiles**

```bash
npx tsc --noEmit 2>&1 | grep -i "BuildingMarker"
```

Expected: No errors referencing BuildingMarker.

**Step 3: Commit**

```bash
git add frontend/src/components/map/BuildingMarker.tsx
git commit -m "refactor: BuildingMarker — L.divIcon → react-map-gl JSX Marker"
```

---

## Task 3: Rewrite POIMarker.tsx

Replace `L.divIcon` HTML string with JSX `<Marker>` + `<Popup>`.

**Files:**
- Rewrite: `frontend/src/components/map/POIMarker.tsx`

**Step 1: Rewrite the component**

Key changes identical to BuildingMarker — remove `L`, use `react-map-gl/maplibre` components, switch lat/lng order.

**Full replacement code:**

```tsx
import { useState } from "react"
import { Marker, Popup } from "react-map-gl/maplibre"
import { useTranslation } from "react-i18next"
import type { CampusPOI } from "@/data/campusPOI"

const CATEGORY_HEX: Record<string, string> = {
  transport: "#3b82f6",
  food: "#f59e0b",
  shop: "#8b5cf6",
  service: "#10b981",
  campus: "#14b8a6",
}

interface POIMarkerProps {
  poi: CampusPOI & { osmName?: string }
}

export function POIMarker({ poi }: POIMarkerProps) {
  const { t } = useTranslation("map")
  const [showPopup, setShowPopup] = useState(false)

  const hex = CATEGORY_HEX[poi.type] ?? "#94a3b8"

  const displayName = poi.i18nKey
    ? t(`poi.items.${poi.i18nKey}.name`, { defaultValue: poi.i18nKey })
    : poi.osmName ?? t(`poi.categories.${poi.type}`)

  const yandexMapsUrl = `https://yandex.ru/maps/?pt=${poi.coords[1]},${poi.coords[0]}&z=17&l=map`

  return (
    <>
      <Marker
        longitude={poi.coords[1]}
        latitude={poi.coords[0]}
        anchor="center"
        onClick={(e) => {
          e.originalEvent.stopPropagation()
          setShowPopup(true)
        }}
      >
        <div
          aria-label={`${displayName} — ${t(`poi.categories.${poi.type}`)}`}
          className="map-poi-marker-3d"
          style={{
            width: 28,
            height: 28,
            background: hex,
            border: "2px solid white",
            borderRadius: "50%",
            boxShadow: "0 1px 4px rgba(0,0,0,0.25)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            cursor: "pointer",
          }}
        >
          <div style={{ width: 8, height: 8, background: "white", borderRadius: "50%" }} />
        </div>
      </Marker>

      {showPopup && (
        <Popup
          longitude={poi.coords[1]}
          latitude={poi.coords[0]}
          anchor="bottom"
          offset={16}
          closeButton={true}
          closeOnClick={false}
          onClose={() => setShowPopup(false)}
          className="map-poi-popup"
        >
          <div className="map-popup-content">
            <p className="font-semibold text-sm mb-0.5">{displayName}</p>
            <p className="text-xs opacity-60 mb-1.5">{t(`poi.categories.${poi.type}`)}</p>
            <a
              href={yandexMapsUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs font-medium"
              style={{ color: "var(--map-accent-line, #14b8a6)" }}
            >
              {t("poi.openInMaps")}
            </a>
          </div>
        </Popup>
      )}
    </>
  )
}
```

**Step 2: Verify TypeScript compiles**

```bash
npx tsc --noEmit 2>&1 | grep -i "POIMarker"
```

**Step 3: Commit**

```bash
git add frontend/src/components/map/POIMarker.tsx
git commit -m "refactor: POIMarker — L.divIcon → react-map-gl JSX Marker"
```

---

## Task 4: Rewrite LeafletMap.tsx → MapLibreMap.tsx

The core migration — replace MapContainer/TileLayer with react-map-gl Map, add 3D buildings layer.

**Files:**
- Delete: `frontend/src/components/map/LeafletMap.tsx`
- Create: `frontend/src/components/map/MapLibreMap.tsx`

**Step 1: Create MapLibreMap.tsx**

Key architecture changes:
- `<MapContainer>` → `<Map>` from `react-map-gl/maplibre`
- `<TileLayer url="...">` → `mapStyle` prop with OpenFreeMap style URL
- `useMap()` from react-leaflet → `useMap()` from react-map-gl (different API!)
- `useMapEvents()` → `<Map onClick>` prop
- `map.flyTo(coords, zoom, {duration})` → `map.flyTo({center: [lng, lat], zoom, pitch, duration})`
  - **CRITICAL**: Leaflet flyTo takes `[lat, lng]`, MapLibre flyTo takes `{center: [lng, lat]}`
- CSS import: `leaflet/dist/leaflet.css` → `maplibre-gl/dist/maplibre-gl.css`
- Add: `<Source>` + `<Layer>` for 3D buildings fill-extrusion
- Add: `initialViewState` with `pitch: 45` and `bearing: 0`
- Dark theme: switch `mapStyle` URL based on theme, NOT CSS filter
- mapRef type: `LeafletMap` → `MapRef` from react-map-gl

**Full replacement code:**

```tsx
/**
 * MapLibreMap.tsx — Geographic map mode using react-map-gl + MapLibre GL + OpenFreeMap.
 *
 * WebGL-powered: 3D buildings via fill-extrusion, vector tiles, native dark theme.
 * Lazy-loaded via React.lazy() in MapFeature.
 *
 * Wave 100 — Leaflet → MapLibre GL migration.
 */

import { useState, useCallback, useMemo } from "react"
import { Map, Source, Layer, Marker, useMap } from "react-map-gl/maplibre"
import type { MapRef, FillExtrusionLayer } from "react-map-gl/maplibre"
import { useTranslation } from "react-i18next"
import { CAMPUS_COORDINATES } from "@/constants/campus"
import { getCampusBuildings, type BuildingLetter, type MapCategory } from "@/data/campusBuildings"
import { CAMPUS_POIS, type CampusPOI } from "@/data/campusPOI"
import { useOverpassPOI } from "@/hooks/useOverpassPOI"
import { BuildingMarker } from "./BuildingMarker"
import { POIMarker } from "./POIMarker"
import { POIControls } from "./POIControls"
import "maplibre-gl/dist/maplibre-gl.css"

/* ── Tile styles ── */
const STYLE_LIGHT = "https://tiles.openfreemap.org/styles/bright"
const STYLE_DARK = "https://tiles.openfreemap.org/styles/bright"
// OpenFreeMap may not have dark; we use bright + 3D layer with dark paint.
// TODO: Switch to dedicated dark style URL when available.

/* ── 3D buildings fill-extrusion ── */
const BUILDINGS_3D_LAYER: FillExtrusionLayer = {
  id: "3d-buildings",
  type: "fill-extrusion",
  source: "openmaptiles",
  "source-layer": "building",
  minzoom: 15,
  paint: {
    "fill-extrusion-color": [
      "interpolate", ["linear"], ["get", "render_height"],
      0, "#d1d5db",
      50, "#9ca3af",
      100, "#6b7280",
    ],
    "fill-extrusion-height": [
      "interpolate", ["linear"], ["zoom"],
      15, 0,
      16, ["get", "render_height"],
    ],
    "fill-extrusion-base": [
      "case",
      [">=", ["get", "zoom"], 16],
      ["get", "render_min_height"],
      0,
    ],
    "fill-extrusion-opacity": 0.7,
  },
}

interface MapLibreMapProps {
  selectedBuilding: BuildingLetter | null
  activeCategory: MapCategory
  highlightedBuilding: BuildingLetter | null
  onSelectBuilding: (letter: BuildingLetter) => void
  /** Forwarded ref for external zoom control */
  mapRef?: React.MutableRefObject<MapRef | null>
  /** Whether dark theme is active */
  isDark?: boolean
}

export function MapLibreMapComponent({
  selectedBuilding,
  activeCategory,
  highlightedBuilding,
  onSelectBuilding,
  mapRef,
  isDark,
}: MapLibreMapProps) {
  const { i18n } = useTranslation("map")

  const buildings = useMemo(
    () => getCampusBuildings(i18n.resolvedLanguage ?? i18n.language),
    [i18n.resolvedLanguage, i18n.language],
  )

  const filteredBuildings = useMemo(() => {
    if (activeCategory === "all") return buildings
    return buildings.filter((b) => b.tags.includes(activeCategory))
  }, [buildings, activeCategory])

  /* ── POI state ── */
  const { pois: overpassPois, isLoading: poisLoading, loadMore, hasLoaded } = useOverpassPOI()
  const [poiCategory, setPoiCategory] = useState<string>("all")

  const allPois = useMemo(() => {
    const base: CampusPOI[] = [...CAMPUS_POIS]
    if (hasLoaded) {
      for (const op of overpassPois) {
        const isDuplicate = base.some((bp) => {
          const dlat = Math.abs(bp.coords[0] - op.coords[0])
          const dlng = Math.abs(bp.coords[1] - op.coords[1])
          return dlat < 0.0005 && dlng < 0.0005
        })
        if (!isDuplicate) base.push(op)
      }
    }
    if (poiCategory === "all") return base
    return base.filter((p) => p.type === poiCategory)
  }, [overpassPois, hasLoaded, poiCategory])

  const handleLoadMore = useCallback(() => {
    loadMore()
  }, [loadMore])

  /* ── Fly to selected building ── */
  const handleMapLoad = useCallback(() => {
    if (selectedBuilding && mapRef?.current) {
      const building = buildings.find((b) => b.letter === selectedBuilding)
      if (building) {
        mapRef.current.flyTo({
          center: [building.geoCoords[1], building.geoCoords[0]],
          zoom: 17,
          pitch: 45,
          duration: 800,
        })
      }
    }
  }, [selectedBuilding, buildings, mapRef])

  const mapStyle = isDark ? STYLE_DARK : STYLE_LIGHT

  return (
    <div className="maplibre-map-wrapper relative h-full min-h-[inherit]">
      <Map
        ref={mapRef}
        initialViewState={{
          longitude: CAMPUS_COORDINATES.lon,
          latitude: CAMPUS_COORDINATES.lat,
          zoom: 16,
          pitch: 45,
          bearing: 0,
        }}
        mapStyle={mapStyle}
        antialias={true}
        style={{ width: "100%", height: "100%", minHeight: "inherit", borderRadius: 12 }}
        attributionControl={true}
        onLoad={handleMapLoad}
        reuseMaps
      >
        {/* 3D building extrusion layer */}
        <Layer {...BUILDINGS_3D_LAYER} />

        {/* Building markers */}
        {filteredBuildings.map((building) => (
          <BuildingMarker
            key={building.letter}
            building={building}
            isSelected={selectedBuilding === building.letter}
            isHighlighted={highlightedBuilding === building.letter}
            onClick={onSelectBuilding}
          />
        ))}

        {/* POI markers */}
        {allPois.map((poi) => (
          <POIMarker key={poi.id} poi={poi} />
        ))}
      </Map>

      {/* POI controls overlay — bottom left */}
      <div className="absolute bottom-4 left-4 z-[500]">
        <POIControls
          activeCategory={poiCategory}
          onCategoryChange={setPoiCategory}
          onLoadMore={handleLoadMore}
          isLoading={poisLoading}
          hasLoadedMore={hasLoaded}
        />
      </div>
    </div>
  )
}

export default MapLibreMapComponent
```

**Step 2: Delete old LeafletMap.tsx**

```bash
rm frontend/src/components/map/LeafletMap.tsx
```

**Step 3: Verify TypeScript (expect errors in MapFeature — fixed in Task 5)**

```bash
npx tsc --noEmit 2>&1 | head -20
```

Expected: Errors in MapFeature.tsx referencing old import path and types.

**Step 4: Commit**

```bash
git add frontend/src/components/map/MapLibreMap.tsx
git add frontend/src/components/map/LeafletMap.tsx  # staged deletion
git commit -m "refactor: LeafletMap → MapLibreMap with 3D fill-extrusion buildings"
```

---

## Task 5: Update MapFeature.tsx

Fix the lazy import, ref type, and zoom/pan bridge methods.

**Files:**
- Modify: `frontend/src/features/map/MapFeature.tsx`

**Step 1: Fix the import at line 27**

```
OLD: import type { Map as LeafletMapType } from "leaflet"
NEW: import type { MapRef } from "react-map-gl/maplibre"
```

**Step 2: Fix the lazy import at line 32**

```
OLD: const LeafletMapComponent = lazy(() => import("@/components/map/LeafletMap"))
NEW: const MapLibreMapComponent = lazy(() => import("@/components/map/MapLibreMap"))
```

**Step 3: Fix the ref type at line 70**

```
OLD: const leafletMapRef = useRef<LeafletMapType | null>(null)
NEW: const mapLibreRef = useRef<MapRef | null>(null)
```

**Step 4: Fix zoom bridge methods (lines 156-178)**

```typescript
// handleZoomIn
OLD: leafletMapRef.current.zoomIn()
NEW: mapLibreRef.current?.zoomIn()

// handleZoomOut
OLD: leafletMapRef.current.zoomOut()
NEW: mapLibreRef.current?.zoomOut()

// handleResetView
OLD: leafletMapRef.current.setView([55.71392, 37.81474], 16)
NEW: mapLibreRef.current?.flyTo({ center: [37.81474, 55.71392], zoom: 16, pitch: 45, bearing: 0, duration: 600 })
```

Note: MapLibre `flyTo` takes `[lng, lat]`, NOT `[lat, lng]`.

**Step 5: Fix the Suspense render block (lines 247-254)**

Replace `LeafletMapComponent` with `MapLibreMapComponent`, replace `mapRef={leafletMapRef}` with `mapRef={mapLibreRef}`.

Add `isDark` prop passed from theme context. Read dark mode from document class:
```typescript
const isDark = typeof document !== "undefined" && document.documentElement.classList.contains("dark")
```
Or use existing theme context if available.

**Step 6: Update all references from `leafletMapRef` → `mapLibreRef`**

Search for every occurrence of `leafletMapRef` in the file and replace with `mapLibreRef`.

**Step 7: Verify TypeScript compiles clean**

```bash
npx tsc --noEmit
```

Expected: 0 errors.

**Step 8: Commit**

```bash
git add frontend/src/features/map/MapFeature.tsx
git commit -m "refactor: MapFeature — wire MapLibreMap, fix ref types and zoom bridge"
```

---

## Task 6: Update map.css

Remove Leaflet-specific CSS, add MapLibre overrides.

**Files:**
- Modify: `frontend/src/styles/tokens/map.css`

**Step 1: Delete Leaflet CSS rules (lines 642-752)**

Remove the entire section starting with `/* LEAFLET OVERRIDES */` through the end of the file. This includes:
- `.map-theme .leaflet-container`
- `.dark .map-theme .leaflet-tile-pane` (CSS filter hack — no longer needed!)
- `.map-theme .leaflet-popup-*`
- `.map-theme .leaflet-control-*`
- `.map-building-marker` / `.map-poi-marker` (L.divIcon reset)

**Step 2: Add MapLibre CSS overrides**

Replace with:

```css
/* ═══════════════════════════════════════════════════════
   MAPLIBRE GL OVERRIDES — scoped to .map-theme
   ═══════════════════════════════════════════════════════ */

.map-theme .maplibregl-map {
  font-family: var(--font-ui), Inter, system-ui, sans-serif;
}

/* Popup → matte card style */
.map-theme .maplibregl-popup-content {
  background: var(--map-poi-popup-bg, var(--bg-surface));
  color: var(--text-primary);
  border-radius: 12px;
  box-shadow: var(--map-poi-popup-shadow, 0 4px 12px rgba(0,0,0,0.1));
  padding: 12px 14px;
  border: none;
  font-size: 0.875rem;
  line-height: 1.4;
}
.map-theme .maplibregl-popup-tip {
  border-top-color: var(--map-poi-popup-bg, var(--bg-surface));
}
.map-theme .maplibregl-popup-close-button {
  color: var(--text-secondary);
  font-size: 1.25rem;
  padding: 4px 8px;
}
.map-theme .maplibregl-popup-close-button:hover {
  color: var(--text-primary);
  background: transparent;
}

/* Attribution → subtle */
.map-theme .maplibregl-ctrl-attrib {
  background: var(--map-leaflet-attribution-bg, rgba(255,255,255,0.8));
  font-size: 0.625rem;
  border-radius: 4px 0 0 0;
}
.map-theme .maplibregl-ctrl-attrib a {
  color: var(--text-secondary);
}

/* Hide default navigation control (we use MapZoomControls) */
.map-theme .maplibregl-ctrl-nav {
  display: none;
}

/* Compass reset styling */
.map-theme .maplibregl-ctrl-compass {
  display: none;
}
```

**Step 3: Keep the shared CSS classes**

These classes are NOT Leaflet-specific and MUST be preserved:
- `.map-poi-controls` — POI controls container
- `.map-poi-chip` — POI category button
- `.map-poi-load-more` — Load more button
- `.map-popup-content` — Popup inner content

**Step 4: Delete the print rule that hides leaflet wrapper**

```
OLD: .leaflet-map-wrapper { display: none; }
NEW: .maplibre-map-wrapper { display: none; }
```

**Step 5: Verify build succeeds**

```bash
npx vite build 2>&1 | tail -5
```

**Step 6: Commit**

```bash
git add frontend/src/styles/tokens/map.css
git commit -m "style: map.css — swap Leaflet overrides → MapLibre GL overrides"
```

---

## Task 7: Full Verification

**Files:** None (read-only verification)

**Step 1: TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 0 errors.

**Step 2: Build + bundle size**

```bash
npx vite build 2>&1 | grep -E "index-.*\.js|MapLibre"
```

Expected:
- Main chunk: ~291 KB (unchanged)
- MapLibreMap chunk: ~215 KB (lazy, was 167 KB with Leaflet)

**Step 3: No Leaflet remnants**

```bash
grep -r "leaflet" --include="*.tsx" --include="*.ts" --include="*.css" frontend/src/ | grep -v node_modules | grep -v ".css.map"
```

Expected: 0 results (no Leaflet references remaining).

**Step 4: i18n balance**

```bash
node -e "
const en = require('./src/i18n/locales/en/map.json');
const ru = require('./src/i18n/locales/ru/map.json');
function count(o){let n=0;for(const k in o){n+=typeof o[k]==='object'?count(o[k]):1}return n}
console.log('EN:', count(en), '| RU:', count(ru), '| Match:', count(en)===count(ru));
"
```

Expected: `EN: 195 | RU: 195 | Match: true`

**Step 5: Visual verification via dev server**

Start dev server and navigate to `/map`:
1. "Map" mode loads → OpenFreeMap vector tiles visible
2. 3D buildings visible when zoom ≥ 16 with pitch 45°
3. 8 building markers with colored circles and letters
4. Click building marker → popup with building info
5. POI markers visible, click → popup with Yandex Maps link
6. "Показать ещё" button → triggers Overpass fetch
7. "Campus" toggle → isometric SVG (unchanged)
8. Mode switch → AnimatePresence transition
9. Zoom controls work (proxy to MapLibre)
10. Dark mode → theme switches (verify no CSS filter hack)

**Step 6: Final commit**

```bash
git add -A
git commit -m "feat(wave100): campus map — Leaflet → MapLibre GL with 3D buildings"
```

---

## Unchanged Files (no edits needed)

| File | Reason |
|------|--------|
| `frontend/src/data/campusBuildings.ts` | Data model unchanged |
| `frontend/src/data/campusPOI.ts` | POI data unchanged |
| `frontend/src/hooks/useOverpassPOI.ts` | Overpass hook unchanged |
| `frontend/src/utils/overpassQuery.ts` | Query builder unchanged |
| `frontend/src/components/map/POIControls.tsx` | Pure UI, no map dependency |
| `frontend/src/components/map/MapZoomControls.tsx` | Pure UI, callbacks from parent |
| `frontend/src/components/map/CampusMapSVG.tsx` | SVG mode unchanged |
| `frontend/src/components/map/FloorPlanSVG.tsx` | Floor plan unchanged |
| `frontend/src/components/map/MapSearchBar.tsx` | Search unchanged |
| `frontend/src/components/map/MapSidebar.tsx` | Sidebar unchanged |
| `frontend/src/components/map/MapLayerToggle.tsx` | Toggle unchanged |
| `frontend/src/i18n/locales/en/map.json` | i18n unchanged |
| `frontend/src/i18n/locales/ru/map.json` | i18n unchanged |

---

## Risk Mitigations

| Risk | Detection | Mitigation |
|------|-----------|------------|
| OpenFreeMap 3D source-layer name wrong | Layer doesn't render → no 3D | Try `"source-layer": "building"` first; fallback `"building_part"`. Check OpenFreeMap TileJSON schema at runtime. |
| `react-map-gl` incompatible with React 19 | `npm install` fails or runtime crash | Check GitHub issues. Fallback: use `maplibre-gl` directly with `useEffect`. |
| MapLibre canvas breaks in Safari private mode | WebGL context lost | MapLibre auto-recovers. Add `onError` handler → show fallback message. |
| Dark OpenFreeMap style doesn't exist | Tiles load in light mode | Use same bright style for both; add CSS `filter` as emergency fallback. |
| 3D buildings too heavy on mobile | Low FPS | Add `maxPitch: 60` and `antialias: false` on mobile via useMediaQuery. |
