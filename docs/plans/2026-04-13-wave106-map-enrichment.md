# Wave 106: Map Enrichment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enrich campus map with building photos (placeholder UI), structured operating hours, expanded room data, and real-time weather atmosphere via Open-Meteo API.

**Architecture:** Four independent features layered onto existing map data model (`campusBuildings.ts`) and UI (`BuildingMarker.tsx`, `MapSidebar.tsx`, `MapFeature.tsx`). Weather hook follows `useOverpassPOI` pattern (TanStack Query + localStorage cache). CSS atmosphere uses `data-weather` attribute on `.map-theme` for token overrides.

**Tech Stack:** React 19, TypeScript, TanStack Query, Open-Meteo API, CSS custom properties, Lucide React icons

---

### Task 1: Structured Operating Hours — Data Model

**Files:**
- Modify: `frontend/src/data/campusBuildings.ts:56-83` (CampusBuilding interface + BuildingStructure)

**Step 1: Add BuildingHours interface and update CampusBuilding**

In `campusBuildings.ts`, add after the `MapCategory` type definition (~line 35):

```ts
export interface BuildingHours {
  weekday: string   // "08:00–22:00"
  saturday: string  // "09:00–18:00"
  sunday: string    // "Closed" (localized from i18n)
}
```

Change `CampusBuilding.hours` from `string` to `BuildingHours`:
```ts
hours: BuildingHours
```

**Step 2: Update LocalizedBuildingMeta and getCampusBuildings**

Change `LocalizedBuildingMeta.hours` from `string` to `BuildingHours` (~line 458):
```ts
hours: BuildingHours
```

In `getCampusBuildings()` (~line 524), the line:
```ts
hours: meta?.hours ?? "",
```
becomes:
```ts
hours: meta?.hours ?? { weekday: "", saturday: "", sunday: "" },
```

**Step 3: Compile check**

Run: `npx tsc --noEmit 2>&1 | head -20`
Expected: errors in MapSidebar.tsx where `building.hours` is used as string — that's expected, fixed in Task 4.

**Step 4: Commit**
```
feat(wave106): structured BuildingHours type
```

---

### Task 2: Structured Operating Hours — i18n Data

**Files:**
- Modify: `frontend/src/i18n/locales/en/map.json`
- Modify: `frontend/src/i18n/locales/ru/map.json`

**Step 1: Update building hours in EN map.json**

Replace each building's `"hours": "..."` string with an object. Example for building А:
```json
"hours": { "weekday": "07:00–22:00", "saturday": "09:00–18:00", "sunday": "Closed" }
```

All 9 buildings:
- А (ГУК): weekday 07:00–22:00, saturday 09:00–18:00, sunday Closed
- Б (Lecture): weekday 08:00–21:00, saturday 09:00–17:00, sunday Closed
- В (Labs): weekday 08:00–20:00, saturday 09:00–16:00, sunday Closed
- Г (Admin): weekday 09:00–18:00, saturday Closed, sunday Closed
- Д (Pool): weekday 07:00–22:00, saturday 08:00–21:00, sunday 09:00–20:00
- Е (Sports): weekday 07:00–22:00, saturday 08:00–21:00, sunday 09:00–20:00
- Ж (Dorm 2): weekday 24/7, saturday 24/7, sunday 24/7
- З (Dorm 6): weekday 24/7, saturday 24/7, sunday 24/7
- И (Business): weekday 09:00–20:00, saturday 10:00–17:00, sunday Closed

**Step 2: Add hours UI keys to EN sidebar section**

```json
"hours": {
  "weekday": "Mon–Fri",
  "saturday": "Sat",
  "sunday": "Sun",
  "openNow": "Open now",
  "closedNow": "Closed"
}
```

**Step 3: Same for RU map.json**

Building hours — same time values but `"sunday": "Закрыто"` for closed buildings.

Hours UI keys:
```json
"hours": {
  "weekday": "Пн–Пт",
  "saturday": "Сб",
  "sunday": "Вс",
  "openNow": "Открыто",
  "closedNow": "Закрыто"
}
```

**Step 4: Commit**
```
feat(wave106): structured hours i18n data (EN+RU)
```

---

### Task 3: Operating Hours — isOpenNow Helper

**Files:**
- Create: `frontend/src/utils/buildingHours.ts`

**Step 1: Create helper**

```ts
import type { BuildingHours } from "@/data/campusBuildings"

/**
 * Check if a building is currently open based on structured hours.
 * Handles "24/7", "Closed"/"Закрыто", and "HH:MM–HH:MM" formats.
 */
export function isOpenNow(hours: BuildingHours): boolean {
  const now = new Date()
  const day = now.getDay() // 0=Sun, 1=Mon...6=Sat

  let todayHours: string
  if (day === 0) todayHours = hours.sunday
  else if (day === 6) todayHours = hours.saturday
  else todayHours = hours.weekday

  if (!todayHours) return false

  const lower = todayHours.toLowerCase()
  if (lower === "24/7") return true
  if (lower === "closed" || lower === "закрыто") return false

  // Parse "HH:MM–HH:MM" format
  const match = todayHours.match(/(\d{1,2}):(\d{2})\s*[–-]\s*(\d{1,2}):(\d{2})/)
  if (!match) return false

  const openMinutes = parseInt(match[1], 10) * 60 + parseInt(match[2], 10)
  const closeMinutes = parseInt(match[3], 10) * 60 + parseInt(match[4], 10)
  const nowMinutes = now.getHours() * 60 + now.getMinutes()

  return nowMinutes >= openMinutes && nowMinutes < closeMinutes
}

/**
 * Get today's hours string from BuildingHours.
 */
export function getTodayHours(hours: BuildingHours): string {
  const day = new Date().getDay()
  if (day === 0) return hours.sunday
  if (day === 6) return hours.saturday
  return hours.weekday
}
```

**Step 2: Compile check**

Run: `npx tsc --noEmit 2>&1 | head -5`

**Step 3: Commit**
```
feat(wave106): isOpenNow + getTodayHours helpers
```

---

### Task 4: Operating Hours — UI in Sidebar + Popup

**Files:**
- Modify: `frontend/src/components/map/MapSidebar.tsx:147-153`
- Modify: `frontend/src/components/map/BuildingMarker.tsx:148-154`

**Step 1: Update MapSidebar hours display**

Replace the hours section (~lines 147-153):
```tsx
{/* Hours — structured Пн-Пт / Сб / Вс */}
<div className="flex flex-col gap-1 text-xs">
  <div className="flex items-center gap-1.5 mb-1">
    <Clock className="h-3.5 w-3.5 text-[var(--color-teal-500)]" />
    <span
      className="font-bold text-[10px] px-1.5 py-0.5 rounded-full"
      style={{
        backgroundColor: isOpenNow(building.hours)
          ? "color-mix(in srgb, var(--color-emerald-500) 15%, transparent)"
          : "color-mix(in srgb, var(--color-rose-500) 15%, transparent)",
        color: isOpenNow(building.hours)
          ? "var(--color-emerald-500)"
          : "var(--color-rose-500)",
      }}
    >
      {isOpenNow(building.hours) ? t("hours.openNow") : t("hours.closedNow")}
    </span>
  </div>
  <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[var(--text-secondary)]">
    <span><span className="font-semibold">{t("hours.weekday")}:</span> {building.hours.weekday}</span>
    <span><span className="font-semibold">{t("hours.saturday")}:</span> {building.hours.saturday}</span>
    <span><span className="font-semibold">{t("hours.sunday")}:</span> {building.hours.sunday}</span>
  </div>
</div>
```

Add import at top:
```ts
import { isOpenNow } from "@/utils/buildingHours"
```

**Step 2: Update BuildingMarker popup hours**

In the stats row, after floors/rooms, add open/closed badge:
```tsx
<span
  className="font-bold text-[10px] px-1.5 py-0.5 rounded-full"
  style={{
    backgroundColor: isOpenNow(building.hours)
      ? "color-mix(in srgb, var(--color-emerald-500) 15%, transparent)"
      : "color-mix(in srgb, var(--color-rose-500) 15%, transparent)",
    color: isOpenNow(building.hours)
      ? "var(--color-emerald-500)"
      : "var(--color-rose-500)",
  }}
>
  {isOpenNow(building.hours) ? t("hours.openNow") : t("hours.closedNow")}
</span>
```

Add import:
```ts
import { isOpenNow } from "@/utils/buildingHours"
```

**Step 3: Compile + build check**

Run: `npx tsc --noEmit && npx vite build 2>&1 | grep "index-"`

**Step 4: Commit**
```
feat(wave106): structured hours UI in sidebar + popup
```

---

### Task 5: Building Photos — Data Model + Placeholder UI

**Files:**
- Modify: `frontend/src/data/campusBuildings.ts:56-83` (CampusBuilding interface)
- Modify: `frontend/src/components/map/BuildingMarker.tsx` (popup photo)
- Modify: `frontend/src/components/map/MapSidebar.tsx` (sidebar photo)
- Modify: `frontend/src/styles/tokens/map.css` (photo CSS)

**Step 1: Add photo field to CampusBuilding**

```ts
/** URL or asset path to building photo (undefined = gradient placeholder) */
photo?: string
```

**Step 2: Add CSS for popup photo**

In map.css, after `.map-popup-card` rules:
```css
/* ── Building photo / placeholder ───────────── */
.map-popup-photo {
  width: 100%;
  height: 100px;
  object-fit: cover;
  display: block;
}

.map-photo-placeholder {
  width: 100%;
  height: 100px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(255, 255, 255, 0.6);
}

.map-sidebar-photo {
  width: 100%;
  height: 140px;
  object-fit: cover;
  display: block;
  border-radius: var(--radius-lg, 0.75rem);
}

.map-sidebar-photo-placeholder {
  width: 100%;
  height: 140px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-lg, 0.75rem);
  color: rgba(255, 255, 255, 0.5);
}
```

**Step 3: Add photo to BuildingMarker popup**

Before the `.map-popup-card` div content, inside the Popup:
```tsx
{/* Photo / placeholder */}
{building.photo ? (
  <img
    src={building.photo}
    alt={building.name}
    className="map-popup-photo"
    loading="lazy"
  />
) : (
  <div
    className="map-photo-placeholder"
    style={{
      background: `linear-gradient(135deg, ${building.colorHex}, color-mix(in srgb, ${building.colorHex} 60%, black))`,
    }}
  >
    <Icon size={32} strokeWidth={1.5} />
  </div>
)}
```

**Step 4: Add photo to MapSidebar**

Before the building header div, add:
```tsx
{/* Building photo / placeholder */}
{building.photo ? (
  <img
    src={building.photo}
    alt={building.name}
    className="map-sidebar-photo"
    loading="lazy"
  />
) : (
  <div
    className="map-sidebar-photo-placeholder"
    style={{
      background: `linear-gradient(135deg, ${building.colorHex}, color-mix(in srgb, ${building.colorHex} 60%, black))`,
    }}
  >
    {/* Category icon from building tags */}
  </div>
)}
```

Note: MapSidebar needs the icon lookup. Import `getPrimaryIcon` from BuildingMarker or extract to shared util.

**Step 5: Compile + build**

Run: `npx tsc --noEmit && npx vite build 2>&1 | grep "index-"`

**Step 6: Commit**
```
feat(wave106): building photo placeholder UI (popup + sidebar)
```

---

### Task 6: Weather Hook — useWeather

**Files:**
- Create: `frontend/src/utils/weatherCodes.ts`
- Create: `frontend/src/hooks/useWeather.ts`

**Step 1: Create WMO code mapping**

`weatherCodes.ts`:
```ts
export type WeatherCondition = "clear" | "cloudy" | "rain" | "snow" | "fog" | "storm"

const WMO_MAP: Record<number, WeatherCondition> = {
  0: "clear", 1: "clear",
  2: "cloudy", 3: "cloudy",
  45: "fog", 48: "fog",
  51: "rain", 53: "rain", 55: "rain",
  56: "rain", 57: "rain",
  61: "rain", 63: "rain", 65: "rain",
  66: "rain", 67: "rain",
  71: "snow", 73: "snow", 75: "snow", 77: "snow",
  80: "rain", 81: "rain", 82: "rain",
  85: "snow", 86: "snow",
  95: "storm", 96: "storm", 99: "storm",
}

export function wmoToCondition(code: number): WeatherCondition {
  return WMO_MAP[code] ?? "clear"
}
```

**Step 2: Create useWeather hook**

`useWeather.ts` — follows `useOverpassPOI` pattern:
```ts
import { useQuery } from "@tanstack/react-query"
import { CAMPUS_COORDINATES } from "@/constants/campus"
import { wmoToCondition, type WeatherCondition } from "@/utils/weatherCodes"

export interface WeatherData {
  temperature: number
  weatherCode: number
  isDay: boolean
  condition: WeatherCondition
}

const CACHE_KEY = "map.weather.cache"
const CACHE_TTL = 30 * 60 * 1000 // 30 minutes

interface CachedWeather {
  timestamp: number
  data: WeatherData
}

function readCache(): WeatherData | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    if (!raw) return null
    const cached = JSON.parse(raw) as CachedWeather
    if (Date.now() - cached.timestamp > CACHE_TTL) {
      localStorage.removeItem(CACHE_KEY)
      return null
    }
    return cached.data
  } catch {
    return null
  }
}

function writeCache(data: WeatherData): void {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify({ timestamp: Date.now(), data }))
  } catch { /* Safari private browsing — RZ-31-03 */ }
}

const API_URL = `https://api.open-meteo.com/v1/forecast?latitude=${CAMPUS_COORDINATES.lat}&longitude=${CAMPUS_COORDINATES.lon}&current=temperature_2m,weather_code,is_day&timezone=Europe/Moscow`

async function fetchWeather(): Promise<WeatherData> {
  const cached = readCache()
  if (cached) return cached

  const res = await fetch(API_URL)
  if (!res.ok) throw new Error(`Weather API ${res.status}`)

  const json = await res.json()
  const current = json.current

  const data: WeatherData = {
    temperature: Math.round(current.temperature_2m),
    weatherCode: current.weather_code,
    isDay: current.is_day === 1,
    condition: wmoToCondition(current.weather_code),
  }

  writeCache(data)
  return data
}

export function useWeather() {
  return useQuery<WeatherData>({
    queryKey: ["campus-weather"],
    queryFn: fetchWeather,
    staleTime: CACHE_TTL,
    gcTime: 2 * CACHE_TTL,
    retry: 1,
    refetchOnWindowFocus: false,
  })
}
```

**Step 3: Compile check**

Run: `npx tsc --noEmit`

**Step 4: Commit**
```
feat(wave106): useWeather hook + WMO code mapping
```

---

### Task 7: Weather Badge Component

**Files:**
- Create: `frontend/src/components/map/MapWeatherBadge.tsx`
- Modify: `frontend/src/i18n/locales/en/map.json` (weather keys)
- Modify: `frontend/src/i18n/locales/ru/map.json` (weather keys)

**Step 1: Add i18n keys**

EN:
```json
"weather": {
  "clear": "Clear",
  "cloudy": "Cloudy",
  "rain": "Rain",
  "snow": "Snow",
  "fog": "Fog",
  "storm": "Storm",
  "loading": "Loading weather...",
  "ariaLabel": "Current weather: {{condition}}, {{temp}}°C"
}
```

RU:
```json
"weather": {
  "clear": "Ясно",
  "cloudy": "Облачно",
  "rain": "Дождь",
  "snow": "Снег",
  "fog": "Туман",
  "storm": "Гроза",
  "loading": "Загрузка погоды…",
  "ariaLabel": "Погода сейчас: {{condition}}, {{temp}}°C"
}
```

**Step 2: Create MapWeatherBadge**

```tsx
import { useTranslation } from "react-i18next"
import {
  Sun, Moon, Cloud, CloudRain, Snowflake, CloudFog, CloudLightning,
  type LucideIcon,
} from "lucide-react"
import { useWeather } from "@/hooks/useWeather"
import type { WeatherCondition } from "@/utils/weatherCodes"

const CONDITION_ICONS: Record<string, { day: LucideIcon; night: LucideIcon }> = {
  clear: { day: Sun, night: Moon },
  cloudy: { day: Cloud, night: Cloud },
  rain: { day: CloudRain, night: CloudRain },
  snow: { day: Snowflake, night: Snowflake },
  fog: { day: CloudFog, night: CloudFog },
  storm: { day: CloudLightning, night: CloudLightning },
}

export function MapWeatherBadge() {
  const { t } = useTranslation("map")
  const { data, isLoading } = useWeather()

  if (isLoading || !data) return null

  const icons = CONDITION_ICONS[data.condition] ?? CONDITION_ICONS.clear
  const Icon = data.isDay ? icons.day : icons.night
  const conditionText = t(`weather.${data.condition}`)

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={t("weather.ariaLabel", {
        condition: conditionText,
        temp: data.temperature,
      })}
      className="map-weather-badge"
    >
      <Icon size={14} strokeWidth={2.5} />
      <span className="font-bold">{data.temperature > 0 ? "+" : ""}{data.temperature}°</span>
      <span className="hidden sm:inline text-[var(--text-tertiary)]">{conditionText}</span>
    </div>
  )
}
```

**Step 3: Add CSS to map.css**

```css
.map-weather-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 9999px;
  font-size: 0.75rem;
  background: var(--map-card-bg);
  box-shadow: var(--map-card-shadow);
  color: var(--text-primary);
}
```

**Step 4: Commit**
```
feat(wave106): MapWeatherBadge component + i18n
```

---

### Task 8: Weather Atmosphere CSS + Wiring

**Files:**
- Modify: `frontend/src/styles/tokens/map.css`
- Modify: `frontend/src/features/map/MapFeature.tsx`

**Step 1: Add weather atmosphere tokens to map.css**

After the dark theme overrides block, add:
```css
/* ═══════════════════════════════════════════════════════
   WEATHER ATMOSPHERE (Open-Meteo)
   data-weather attr set by MapFeature from useWeather.
   ═══════════════════════════════════════════════════════ */

.map-theme[data-weather="cloudy"] {
  --map-orb-1: color-mix(in srgb, var(--color-slate-400) 8%, transparent);
  --map-orb-2: color-mix(in srgb, var(--color-slate-300) 6%, transparent);
  --map-hero-orb: color-mix(in srgb, var(--color-slate-400) 8%, transparent);
}

.map-theme[data-weather="rain"] {
  --map-orb-1: color-mix(in srgb, var(--color-blue-400) 12%, transparent);
  --map-orb-2: color-mix(in srgb, var(--color-blue-300) 8%, transparent);
  --map-hero-orb: color-mix(in srgb, var(--color-blue-400) 10%, transparent);
}

.map-theme[data-weather="snow"] {
  --map-orb-1: color-mix(in srgb, var(--color-sky-200) 15%, transparent);
  --map-orb-2: color-mix(in srgb, var(--color-sky-100) 10%, transparent);
  --map-hero-orb: color-mix(in srgb, var(--color-sky-300) 12%, transparent);
}

.map-theme[data-weather="fog"] {
  --map-orb-1: color-mix(in srgb, var(--color-slate-300) 6%, transparent);
  --map-orb-2: color-mix(in srgb, var(--color-slate-200) 4%, transparent);
  --map-hero-orb: color-mix(in srgb, var(--color-slate-300) 5%, transparent);
}

.map-theme[data-weather="storm"] {
  --map-orb-1: color-mix(in srgb, var(--color-violet-400) 12%, transparent);
  --map-orb-2: color-mix(in srgb, var(--color-violet-300) 8%, transparent);
  --map-hero-orb: color-mix(in srgb, var(--color-violet-400) 10%, transparent);
}

/* Dark mode weather adjustments */
.dark .map-theme[data-weather="cloudy"] {
  --map-orb-1: color-mix(in srgb, var(--color-slate-500) 12%, transparent);
}

.dark .map-theme[data-weather="rain"] {
  --map-orb-1: color-mix(in srgb, var(--color-blue-500) 14%, transparent);
}

.dark .map-theme[data-weather="snow"] {
  --map-orb-1: color-mix(in srgb, var(--color-sky-300) 18%, transparent);
}

.dark .map-theme[data-weather="storm"] {
  --map-orb-1: color-mix(in srgb, var(--color-violet-500) 16%, transparent);
}
```

**Step 2: Wire useWeather in MapFeature.tsx**

Add imports:
```ts
import { useWeather } from "@/hooks/useWeather"
import { MapWeatherBadge } from "@/components/map/MapWeatherBadge"
```

Inside MapFeature, add:
```ts
const { data: weatherData } = useWeather()
```

On the root div, add `data-weather` attribute:
```tsx
<div
  className="map-theme aurora-mesh relative w-full ..."
  data-weather={weatherData?.condition}
>
```

Add `MapWeatherBadge` in the header area (inside the first FadeSection, next to MapHeader):
```tsx
<MapHeader />
<MapWeatherBadge />
```

**Step 3: Compile + build + bundle check**

Run: `npx tsc --noEmit && npx vite build 2>&1 | grep "index-"`
Expected: chunk <500 KB

**Step 4: Commit**
```
feat(wave106): weather atmosphere CSS + MapFeature wiring
```

---

### Task 9: Expand Room Data

**Files:**
- Modify: `frontend/src/data/campusBuildings.ts` (CAMPUS_STRUCTURE rooms)
- Modify: `frontend/src/i18n/locales/en/map.json` (rooms section)
- Modify: `frontend/src/i18n/locales/ru/map.json` (rooms section)

**Step 1: Expand rooms in CAMPUS_STRUCTURE**

Add more rooms per floor to bring total from ~54 to ~120. Base on the real GUU room numbering found via research where available. Use realistic types (lecture halls on low floors, offices on high floors).

Key data from research:
- А (ГУК): ГУ-229 (floor 2, admin), ГУ-506/509 (floor 5, admin), У-464 (floor 4, office)
- В (Labs): ЛК-204/206/207/212/216 (floor 2), ЛК-304/308/310/312 (floor 3), ЛК-402/431/440 (floor 4), ЛК-645 (floor 6)
- Г (Admin): А-319 (floor 3, admin)

Add 3-5 rooms per floor for buildings А-В-Г. Keep sports/dorm buildings sparse (2 rooms/floor).

**Step 2: Add room names to i18n**

For rooms with known real names, add to `rooms` section:
```json
"А-229": { "name": "Admissions Office (ГУ-229)" },
"В-204": { "name": "Computer Lab (ЛК-204)" },
"В-304": { "name": "Dept. of International Business (ЛК-304)" }
```
etc.

**Step 3: Compile check + commit**
```
feat(wave106): expand room data (~54 → ~120 rooms)
```

---

### Task 10: Final Verification

**Step 1:** `npx tsc --noEmit` — 0 errors
**Step 2:** `npx vite build 2>&1 | grep "index-"` — chunk <500 KB
**Step 3:** Preview verification — start dev server, navigate to /map, check:
- Building popup shows photo placeholder + open/closed badge
- Sidebar shows structured hours (Пн-Пт / Сб / Вс)
- Weather badge appears with temperature
- Backdrop orbs reflect weather condition
- Dark mode works
- Expanded rooms appear in floor selector

**Step 4: Final commit**
```
feat(wave106): map enrichment — photos, hours, weather, rooms
```
