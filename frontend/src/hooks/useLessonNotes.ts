/**
 * useLessonNotes — IndexedDB-backed lesson notes.
 * Wave 66 (Idea #12). Uses idb-keyval (already in project).
 */
import { useState, useEffect, useCallback, useRef } from "react"
import { get, set, del } from "idb-keyval"

const KEY_PREFIX = "schedule:notes:"

export interface LessonNote {
  text: string
  updatedAt: number
}

/**
 * Hook for reading/writing a note for a specific lesson.
 * Auto-saves on 300ms debounce.
 */
export function useLessonNotes(lessonId: string | null | undefined) {
  const [note, setNoteState] = useState<LessonNote | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  // Load note from IndexedDB
  useEffect(() => {
    if (!lessonId) {
      setNoteState(null)
      return
    }
    setIsLoading(true)
    get<LessonNote>(`${KEY_PREFIX}${lessonId}`)
      .then((stored) => setNoteState(stored ?? null))
      .catch(() => setNoteState(null))
      .finally(() => setIsLoading(false))
  }, [lessonId])

  // Set note with debounced save to IndexedDB
  const setNote = useCallback(
    (text: string) => {
      if (!lessonId) return
      const updated: LessonNote = { text, updatedAt: Date.now() }
      setNoteState(updated)

      // Debounce IndexedDB write
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(() => {
        if (text.trim()) {
          set(`${KEY_PREFIX}${lessonId}`, updated).catch((err) => console.warn("[schedule:notes]", err))
        } else {
          del(`${KEY_PREFIX}${lessonId}`).catch((err) => console.warn("[schedule:notes]", err))
        }
      }, 300)
    },
    [lessonId],
  )

  // Clear note
  const clearNote = useCallback(() => {
    if (!lessonId) return
    setNoteState(null)
    del(`${KEY_PREFIX}${lessonId}`).catch((err) => console.warn("[schedule:notes]", err))
  }, [lessonId])

  // Cleanup debounce timer
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [])

  return {
    note,
    isLoading,
    setNote,
    clearNote,
    hasNote: !!note?.text?.trim(),
  }
}

/**
 * Check if a lesson has a note (lightweight — for card indicators).
 * Returns a Map for batch checking.
 */
export function useLessonNotesMap(lessonIds: string[]) {
  const [notesMap, setNotesMap] = useState<Map<string, boolean>>(new Map())

  useEffect(() => {
    if (lessonIds.length === 0) return
    const map = new Map<string, boolean>()
    Promise.all(
      lessonIds.map(async (id) => {
        const stored = await get<LessonNote>(`${KEY_PREFIX}${id}`).catch(() => null)
        map.set(id, !!stored?.text?.trim())
      }),
    ).then(() => setNotesMap(new Map(map)))
  }, [lessonIds.join(",")]) // eslint-disable-line react-hooks/exhaustive-deps -- stable join key

  return notesMap
}
