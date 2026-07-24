/**
 * useLessonNotes — IndexedDB-backed lesson notes.
 * Wave 66 (Idea #12). Uses idb-keyval (already in project).
 */
import { useState, useEffect, useCallback, useRef } from "react"
import { get, set, del } from "idb-keyval"
import { logError } from "@/app/logger"
import { getDatabase } from "@/db"

const KEY_PREFIX = "schedule:notes:"

export interface LessonNote {
  text: string
  updatedAt: number
}

/**
 * Hook for reading/writing a note for a specific lesson.
 * Auto-saves on 300ms debounce to RxDB and IndexedDB.
 */
export function useLessonNotes(lessonId: string | null | undefined) {
  const [note, setNoteState] = useState<LessonNote | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  // Load note from RxDB / IndexedDB
  useEffect(() => {
    if (!lessonId) {
      setNoteState(null)
      return
    }
    setIsLoading(true)

    let isMounted = true
    async function fetchNote() {
      try {
        const db = await getDatabase()
        const rxNote = await db.notes.findOne(lessonId).exec()
        if (rxNote) {
          if (isMounted) setNoteState({ text: rxNote.text, updatedAt: rxNote.updated_at })
          return
        }
      } catch {
        /* fallback to idb-keyval */
      }

      // Fallback to idb-keyval
      try {
        const stored = await get<LessonNote>(`${KEY_PREFIX}${lessonId}`)
        if (isMounted) setNoteState(stored ?? null)
      } catch {
        if (isMounted) setNoteState(null)
      }
    }

    fetchNote().finally(() => {
      if (isMounted) setIsLoading(false)
    })

    return () => {
      isMounted = false
    }
  }, [lessonId])

  // Set note with debounced save to RxDB & IndexedDB
  const setNote = useCallback(
    (text: string) => {
      if (!lessonId) return
      const updated: LessonNote = { text, updatedAt: Date.now() }
      setNoteState(updated)

      // Debounce writes
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(() => {
        if (text.trim()) {
          getDatabase()
            .then((db) =>
              db.notes.upsert({
                id: lessonId,
                lesson_id: lessonId,
                text,
                updated_at: updated.updatedAt,
                is_synced: false,
              })
            )
            .catch(() => {})

          set(`${KEY_PREFIX}${lessonId}`, updated).catch((err) => logError("[schedule:notes]", err))
        } else {
          getDatabase()
            .then(async (db) => {
              const rxNote = await db.notes.findOne(lessonId).exec()
              if (rxNote) await rxNote.remove()
            })
            .catch(() => {})

          del(`${KEY_PREFIX}${lessonId}`).catch((err) => logError("[schedule:notes]", err))
        }
      }, 300)
    },
    [lessonId]
  )

  // Clear note
  const clearNote = useCallback(() => {
    if (!lessonId) return
    setNoteState(null)
    getDatabase()
      .then(async (db) => {
        const rxNote = await db.notes.findOne(lessonId).exec()
        if (rxNote) await rxNote.remove()
      })
      .catch((err) => logError("[schedule:notes:rxdb]", err))
    del(`${KEY_PREFIX}${lessonId}`).catch((err) => logError("[schedule:notes]", err))
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
 * Returns a Map for batch checking using RxDB.
 */
export function useLessonNotesMap(lessonIds: string[]) {
  const [notesMap, setNotesMap] = useState<Map<string, boolean>>(new Map())

  // CQ-72-01: extract dep key — .join() produces a stable primitive string
  const depKey = lessonIds.join(",")

  useEffect(() => {
    if (lessonIds.length === 0) return
    let isMounted = true

    async function loadNotesMap() {
      const map = new Map<string, boolean>()
      try {
        const db = await getDatabase()
        const rxNotes = await db.notes.find({ selector: { id: { $in: lessonIds } } }).exec()
        rxNotes.forEach((n) => {
          if (n.text?.trim()) map.set(n.id, true)
        })
      } catch {
        /* fallback below */
      }

      await Promise.all(
        lessonIds.map(async (id) => {
          if (!map.has(id)) {
            const stored = await get<LessonNote>(`${KEY_PREFIX}${id}`).catch(() => null)
            map.set(id, !!stored?.text?.trim())
          }
        })
      )

      if (isMounted) setNotesMap(map)
    }

    loadNotesMap()

    return () => {
      isMounted = false
    }
  }, [depKey]) // eslint-disable-line react-hooks/exhaustive-deps -- stable join key

  return notesMap
}
