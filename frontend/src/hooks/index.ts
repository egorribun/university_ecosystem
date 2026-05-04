/**
 * @fileoverview hooks/ barrel — public surface of shared, cross-cutting React hooks.
 *
 * Exports every non-test hook in the root of `frontend/src/hooks/` plus the
 * named/typed surface of each one. Sub-folders (`auth/`, `features/`, `ui/`)
 * have their own internal organisation and are NOT re-exported here —
 * consumers should reach into them directly:
 *
 *     import { useAuthApi } from "@/hooks/auth/useAuthApi"
 *     import { useMessengerController } from "@/hooks/features/useMessengerController"
 *     import { useSlidingIndicator } from "@/hooks/ui/useSlidingIndicator"
 *
 * For top-level shared hooks the barrel provides one stable import surface:
 *
 *     import { useDebounced, useFocusTrap, useURLState } from "@/hooks"
 *
 * Adding a new hook? Append a re-export line in alphabetical order.
 * - Files exporting only named symbols use `export * from "./<file>"` —
 *   that picks up every named export and TS type alias on the way out.
 * - Files exporting a default symbol additionally need
 *   `export { default as <hookName> } from "./<file>"` because `export *`
 *   does not forward defaults. The four current defaults are tagged below.
 *
 * Wave-tracked hooks (Schedule, News, Events, Activity, Map per CLAUDE.md
 * Gotchas) sometimes move between this barrel and their feature folders.
 * If a hook leaves the root, drop its entry here and let CI's lint +
 * tsc surface any stale imports.
 */

export * from "./useActivityComparative"
export * from "./useActivityData"
export { default as useActivityData } from "./useActivityData"
export * from "./useAnimatedFloat"
export * from "./useArticleHeadings"
export * from "./useArticleNavigation"
export * from "./useBookmarks"
export * from "./useChatWebSocket"
export * from "./useClassReminders"
export * from "./useClock"
export * from "./useCountUp"
export * from "./useDashboardEvents"
export * from "./useDashboardNews"
export * from "./useDashboardSchedule"
export * from "./useDashboardStories"
export * from "./useDebounced"
export * from "./useEventCardLogic"
export * from "./useEventRegistration"
export * from "./useEventsKeyboardNav"
export * from "./useFocusTrap"
export { default as useFocusTrap } from "./useFocusTrap"
export * from "./useGreeting"
export * from "./useHaptics"
export * from "./useIntersectionObserver"
export * from "./useLessonNotes"
export * from "./useLocalStorage"
export * from "./useMapEvents"
export * from "./useMapKeyboardShortcuts"
export * from "./useMapWeather"
export * from "./useMediaQuery"
export { default as useMediaQuery } from "./useMediaQuery"
export * from "./useNewsInteraction"
export * from "./useNewsKeyboardNav"
export * from "./useNextLesson"
export * from "./useNotifications"
export * from "./useNowPlaying"
export * from "./useOnlineStatus"
export * from "./usePushPreferences"
export * from "./usePushSync"
export * from "./useRelatedEvents"
export * from "./useRelatedNews"
export * from "./useRouteType"
export * from "./useScheduleConfig"
export * from "./useScheduleData"
export * from "./useScheduleKeyboardNav"
export * from "./useScheduleReminders"
export * from "./useScheduleTime"
export * from "./useScheduleURLSync"
export * from "./useScrollRestoration"
export { default as useScrollRestoration } from "./useScrollRestoration"
export * from "./useScrollToElement"
export * from "./useSeason"
export * from "./useShare"
export * from "./useSwipe"
export * from "./useSwipeGesture"
export * from "./useTilt"
export * from "./useTimeOfDay"
export * from "./useURLState"
export * from "./useWeather"
