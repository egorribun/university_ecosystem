/**
 * News Feature
 *
 * Handles university news: listing, detail view, likes, comments.
 */

// Re-export components from existing locations
export { default as NewsCard } from "@/components/NewsCard"

// Hooks
export { useDashboardNews } from "@/hooks/useDashboardNews"
export { useNewsInteraction } from "@/hooks/useNewsInteraction"

// Types
