/**
 * Dashboard Feature
 *
 * Handles main dashboard: stories, widgets, quick access.
 */

// Re-export components from existing locations
export { default as DashboardStories } from "@/components/DashboardStories"
export { default as WeatherWidget } from "@/components/WeatherWidget"

// Hooks
export { useDashboardStories } from "@/hooks/useDashboardStories"
export { useWeather } from "@/hooks/useWeather"
export { useNowPlaying } from "@/hooks/useNowPlaying"
