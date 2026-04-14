# Wave 47 — Dashboard Delight II

## Context
Wave 46 added 6 interactive features (greeting palette, SkeletonMorph, parallax, 3D tilt, glass toast, schedule timeline). Wave 47 continues with 5 data-driven and ambient polish features.

## Features

### 6. Greeting Easter Eggs
Calendar-based special greetings: Jan 1, Sep 1 (Knowledge Day), Dec 31. Extends `useGreeting()` with holiday map. CSS sparkle animation on special days.

### 7. Hero Ambient Glow
Greeting-palette-colored outer `box-shadow` on Hero card. Pure CSS via `--hero-grad-start`.

### 8. Card Content Transitions
AnimatePresence + stagger on EventsCard scope toggle and NewsCard list. Entry: opacity+translateY, 200ms, 40ms stagger.

### 9. Refetch Shimmer
CSS shimmer sweep on cards during `isFetching && !isLoading`. `@keyframes` left-to-right gradient sweep, 1.2s.

### 10. Weather-Aware Ambient Particles
CSS-only rain/snow/sun particles in dashboard backdrop. Maps `WeatherAnimationVariant` to particle effects. ~20 elements, all `@keyframes`.

## Files
- Modify: `useGreeting.ts`, `DashboardHero.tsx`, `dashboard-theme.css`, `EventsCard.tsx`, `NewsCard.tsx`, `Dashboard.tsx`, `_micro-interactions.css`
- Create: `WeatherAmbient.tsx`
