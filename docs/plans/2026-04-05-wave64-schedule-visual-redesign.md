# Wave 64: Schedule Page Visual Redesign

## Problem
The Schedule page looks cheap and unpolished compared to Dashboard and News:
- Grid table doesn't fit all 6 days (204px per column at 1280px)
- Cards have 8% transparent backgrounds vs Dashboard's 92%+ opaque matte
- Padding is cramped: `p-2`/`p-3` vs Dashboard's `p-6`/`p-7`
- Only `border-left: 3px` accent — no depth, shadow, or inner glow
- Badges are flat `outline` — no volumetric feel
- Colors don't match Dashboard/News palette
- Hover effects minimal (-1px vs -3px lift)

## Design

### 1. LessonCard — Premium Matte Cards
- Background: `glass-layer-matte` with lesson-type color tinting (5%)
- Border: top gradient accent (2px, lesson-type color) + thin full border
- Shadows: `shadow-matte-card` + `inset 0 1px 0 white/4%` inner glow
- Padding: `p-4` min, `p-5` on wide screens
- Hover: `-2px` lift + shadow growth + border glow
- Type badge: matte solid (not outline) with inner highlight
- Time badge: subtle matte pill, no border

### 2. Desktop Table — Horizontal Scroll
- Column min-width: `minmax(220px, 1fr)`
- Container: `overflow-x: auto` with scroll-snap
- Sticky row numbers: `position: sticky; left: 0`
- Sticky headers: `position: sticky; top: 0`
- Fade edges: gradient mask when scrollable
- At 1440px+: all 6 columns fit without scroll

### 3. Column Headers — Premium Style
- Matte background with glass-noise texture
- Today: gradient accent line + brand pill badge
- Subtle gradient separators between days

### 4. Empty Cells
- Remove dashed border → subtle solid line
- Diagonal dots pattern via CSS background
- Hover: highlight + "+" icon for admin/teacher

### 5. Break Indicators
- Compact centered pill badge (no timeline dots in table)
- Matte warning-bg badge style
- Proper spacing from cards

### 6. Color Palette Sync
- Lecture: brand-main blue, 5% bg tint
- Practice: emerald-500, 5% bg tint
- Lab: amber-500, 5% bg tint
- Project: violet-500, 5% bg tint (from indigo)
- Conflict: rose-500, 8% bg tint + pulsing border

### 7. Mobile DayColumn
- Padding: `p-5 sm:p-6`
- Card gap: `gap-4`
- Day header: `text-xl font-black`
- Full-width matte cards

### 8. Skeleton Loading
- Updated to match new wider layout

## Files Modified
- `frontend/src/styles/tokens/schedule.css` — complete token overhaul
- `frontend/src/components/schedule/LessonCard.tsx` — premium matte card
- `frontend/src/components/schedule/ScheduleDesktopTable.tsx` — horizontal scroll + sticky
- `frontend/src/components/schedule/DayColumn.tsx` — mobile spacing
- `frontend/src/components/schedule/ScheduleListView.tsx` — consistent card style
- `frontend/src/components/schedule/ScheduleSkeleton.tsx` — updated layout
- `frontend/src/components/schedule/ScheduleHeader.tsx` — style alignment
