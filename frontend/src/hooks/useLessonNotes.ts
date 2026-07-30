/**
 * useLessonNotes — IndexedDB-backed lesson notes.
 * Wave 66 (Idea #12). Uses idb-keyval (already in project).
 */
import { useState, useEffect, useCallback, useRef } from "react"
import { get, set, del } from "idb-keyval"
import { logError } from "@/app/logger"
import { getDatabase } from "@/db"
import { useDebounced } from "./useDebounced"

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
  const debouncedNote = useDebounced(note, 300)
  const lastSavedRef = useRef<LessonNote | null>(null)

  // Load note from RxDB / IndexedDB
  useEffect(() => {
    if (!lessonId) {
      setNoteState(null)
      lastSavedRef.current = null
      return
    }
    const currentLessonId = lessonId
    setIsLoading(true)

    let isMounted = true
    async function fetchNote() {
      try {
        const db = await getDatabase()
        const rxNote = await db.notes.findOne(currentLessonId).exec()
        if (rxNote) {
          if (isMounted) {
            const loaded = { text: rxNote.text, updatedAt: rxNote.updated_at }
            setNoteState(loaded)
            lastSavedRef.current = loaded
          }
          return
        }
      } catch {
        /* fallback to idb-keyval */
      }

      // Fallback to idb-keyval
      try {
        const stored = await get<LessonNote>(`${KEY_PREFIX}${currentLessonId}`)
        if (isMounted) {
          const loaded = stored ?? null
          setNoteState(loaded)
          lastSavedRef.current = loaded
        }
      } catch {
        if (isMounted) {
          setNoteState(null)
          lastSavedRef.current = null
        }
      }
    }

    fetchNote().finally(() => {
      if (isMounted) setIsLoading(false)
    })

    return () => {
      isMounted = false
    }
  }, [lessonId])

  // Save debounced note changes to RxDB & IndexedDB
  useEffect(() => {
    if (!lessonId || debouncedNote === lastSavedRef.current) return
    lastSavedRef.current = debouncedNote
    const currentLessonId = lessonId

    if (debouncedNote && debouncedNote.text.trim()) {
      getDatabase()
        .then((db) =>
          db.notes.upsert({
            id: currentLessonId,
            lesson_id: currentLessonId,
            text: debouncedNote.text,
            updated_at: debouncedNote.updatedAt,
            is_synced: false,
          })
        )
        .catch(() => {})

      set(`${KEY_PREFIX}${currentLessonId}`, debouncedNote).catch((err) =>
        logError("[schedule:notes]", err)
      )
    } else {
      getDatabase()
        .then(async (db) => {
          const rxNote = await db.notes.findOne(currentLessonId).exec()
          if (rxNote) await rxNote.remove()
        })
        .catch(() => {})

      del(`${KEY_PREFIX}${currentLessonId}`).catch((err) => logError("[schedule:notes]", err))
    }
  }, [debouncedNote, lessonId])

  // Set note with state update
  const setNote = useCallback(
    (text: string) => {
      if (!lessonId) return
      const updated: LessonNote = { text, updatedAt: Date.now() }
      setNoteState(updated)
    },
    [lessonId]
  )

  // Clear note
  const clearNote = useCallback(() => {
    if (!lessonId) return
    const currentLessonId = lessonId
    lastSavedRef.current = null
    setNoteState(null)
    getDatabase()
      .then(async (db) => {
        const rxNote = await db.notes.findOne(currentLessonId).exec()
        if (rxNote) await rxNote.remove()
      })
      .catch((err) => logError("[schedule:notes:rxdb]", err))
    del(`${KEY_PREFIX}${currentLessonId}`).catch((err) => logError("[schedule:notes]", err))
  }, [lessonId])

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
