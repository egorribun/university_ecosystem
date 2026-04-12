# Design: Leaflet → MapLibre GL Migration

## Context
Wave 99 added a Leaflet map mode (react-leaflet + OpenStreetMap raster tiles) alongside the isometric SVG campus view. While functional, Leaflet renders flat raster tiles with no 3D support, requiring a CSS `filter: invert(1) hue-rotate(180deg)` hack for dark mode. MapLibre GL JS provides WebGL-accelerated vector tiles, native 3D fill-extrusion for buildings, smooth continuous zoom, pitch/bearing controls, and native dark theme support — a significant UX upgrade.

## Decision
Migrate from `leaflet` + `react-leaflet` to `maplibre-gl` + `react-map-gl/maplibre`.

## Key Choices
- **React binding:** `react-map-gl/maplibre` (vis.gl) — industry standard, 441+ code snippets
- **Tile source:** OpenFreeMap vector tiles (`tiles.openfreemap.org`) — free, no API key, building height data included
- **3D buildings:** fill-extrusion layer from OpenFreeMap `building` source-layer. All buildings render in 3D; GUU buildings highlighted with custom colors
- **Dark theme:** Native OpenFreeMap dark style URL — no CSS filter hack
- **Camera default:** pitch 45°, bearing 0°, zoom 16. User can freely rotate/tilt
- **Lazy loading:** React.lazy() boundary preserved — maplibre-gl CSS/JS only loaded on "Map" mode activation

## Component Mapping (1:1)
| react-leaflet | react-map-gl/maplibre |
|---|---|
| `<MapContainer>` | `<Map>` |
| `<TileLayer url>` | `mapStyle` prop (style URL) |
| `<Marker icon={L.divIcon()}>` | `<Marker>` with JSX children |
| `<Popup>` | `<Popup>` with JSX children |
| `useMap()` | `useMap()` |
| `useMapEvents()` | `<Map onClick/onMove/...>` props |

## Bundle Impact
- Remove: leaflet (42 KB) + react-leaflet (12 KB) = 54 KB
- Add: maplibre-gl (~200 KB) + react-map-gl (~15 KB) = ~215 KB
- Net: +161 KB in lazy chunk. Main chunk unchanged (~291 KB).
- All behind React.lazy() — no impact on initial page load

## Files Changed
| Action | File |
|---|---|
| REWRITE | `LeafletMap.tsx` → `MapLibreMap.tsx` |
| REWRITE | `BuildingMarker.tsx` |
| REWRITE | `POIMarker.tsx` |
| MODIFY | `MapFeature.tsx` |
| MODIFY | `MapZoomControls.tsx` |
| MODIFY | `map.css` |
| NO CHANGE | `campusPOI.ts`, `useOverpassPOI.ts`, `overpassQuery.ts`, `POIControls.tsx`, `campusBuildings.ts`, i18n |

## Risks
- OpenFreeMap dark style availability → fallback to bright + CSS filter
- MapLibre ~200 KB → behind lazy boundary
- react-map-gl React 19 compat → check at install time
