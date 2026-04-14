/**
 * scheduleTransition.ts — View Transition state for lesson card morph.
 * Stores the active lesson ID so only ONE element has view-transition-name
 * at any time (same pattern as newsTransition.ts).
 * Wave 66 (Idea #19)
 */

let activeLessonTransitionId: string | null = null

export function setScheduleTransitionId(id: string | null): void {
  activeLessonTransitionId = id
}

export function getScheduleTransitionId(): string | null {
  return activeLessonTransitionId
}

export function clearScheduleTransition(): void {
  activeLessonTransitionId = null
}
