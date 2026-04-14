# Wave 106: Map Enrichment — Design Document

**Date**: 2026-04-13
**Scope**: Building photos, expanded rooms, structured hours, weather atmosphere

## Context

The campus map (Waves 99-105) has MapLibre GL 3D, 9 buildings, POI markers, search, animations. This wave enriches the data layer and adds environmental awareness.

## Feature 1: Building Photos

**Data model change** — `CampusBuilding` gains:
```ts
photo?: string  // URL or asset path to building photograph
```

**Popup card** (BuildingMarker.tsx):
- Image 280×100px before header, `object-fit: cover`, rounded top corners
- Fallback when `photo` is undefined: gradient placeholder `linear-gradient(135deg, colorHex, darken(colorHex, 20%))` with centered Lucide category icon

**Sidebar** (MapSidebar.tsx):
- Image 100% width × 140px in header area
- Same fallback placeholder

**CSS**: `.map-popup-photo` class in map.css — aspect-ratio, overflow clip, border-radius

**i18n**: None (visual-only feature)

## Feature 2: Expanded Room Data

**Data source**: Public GUU information (guu.ru departments, contacts). Real room prefix convention: ГУ (Main), ЛК (Labs), П (Lecture), А (Admin). Confirmed rooms: ГУ-229, ГУ-506, ГУ-509, ЛК-204/206/207/212/216/304/308/310/312/402/431/440/645, А-319.

**Approach**: Keep current letter-based IDs (А-101) for consistency. Add real names where known (e.g., А-229 name="ГУ-229 — Приёмная комиссия"). Expand from ~54 to ~120-150 rooms with realistic structure (5-10 rooms per floor).

**Files modified**: `campusBuildings.ts` (CAMPUS_STRUCTURE), `en/map.json` + `ru/map.json` (rooms section)

## Feature 3: Structured Operating Hours

**Data model change** — `hours: string` replaced with:
```ts
interface BuildingHours {
  weekday: string   // "08:00–22:00"
  saturday: string  // "09:00–18:00"
  sunday: string    // "Closed"
}
```

**Helper**: `isOpenNow(hours: BuildingHours): boolean` — compares current day/time against schedule.

**Sidebar UI**: Three-line display (Пн-Пт / Сб / Вс) with green/red "Open now" / "Closed" badge.

**Popup UI**: Compact — current day hours + status badge only.

**i18n keys**: `hours.weekday`, `hours.saturday`, `hours.sunday`, `hours.openNow`, `hours.closedNow`

## Feature 4: Weather Atmosphere (Open-Meteo)

**API**: `GET https://api.open-meteo.com/v1/forecast?latitude=55.7144&longitude=37.8148&current=temperature_2m,weather_code,is_day`
- Free, no API key, 10K requests/day
- Returns WMO weather code, temperature, is_day flag

**Hook** — `useWeather.ts`:
```ts
interface WeatherData {
  temperature: number
  weatherCode: number
  isDay: boolean
  condition: "clear" | "cloudy" | "rain" | "snow" | "fog" | "storm"
}
```
- TanStack Query: staleTime 30min, retry 1
- localStorage cache (30min TTL, same pattern as useOverpassPOI)
- Fallback on error: condition="clear", temperature=null

**WMO code mapping**:
- 0-1 → clear, 2-3 → cloudy, 45-48 → fog
- 51-67 → rain, 71-77 → snow, 80-82 → rain, 85-86 → snow, 95-99 → storm

**CSS atmosphere** — `data-weather` attribute on `.map-theme`:
- clear: default warm teal orbs
- cloudy: muted slate orbs
- rain: blue-cold orbs
- snow: white-blue orbs, cold palette
- fog: low contrast, soft orbs
- storm: violet orbs, darker bg

**Weather badge** — `MapWeatherBadge.tsx`:
- Small chip in map header area
- Lucide icon (Sun/Cloud/CloudRain/Snowflake/CloudFog/CloudLightning) + temperature
- Matte chip style, role="status", aria-live="polite"

## File Impact Summary

| Category | Files | Changes |
|----------|-------|---------|
| Data | campusBuildings.ts | +photo field, +BuildingHours type, expand rooms |
| Components | BuildingMarker.tsx, MapSidebar.tsx | Photo UI + hours UI |
| New component | MapWeatherBadge.tsx | Weather chip |
| New hook | useWeather.ts | Open-Meteo fetch + cache |
| New util | weatherCodes.ts | WMO → condition mapping |
| CSS | map.css | Photo styles, weather atmosphere tokens, badge |
| i18n | en/map.json, ru/map.json | Hours keys, weather keys, new room names |
| Orchestrator | MapFeature.tsx | Wire useWeather, pass data-weather attr |

**Dependencies**: 0 new npm packages
**Bundle impact**: ~2-3 KB (weather hook + badge component)
