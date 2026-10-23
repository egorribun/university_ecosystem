/** Account-scoped offline lesson notes. Legacy lesson-only keys are never read. */
import { useState, useEffect, useCallback, useRef } from "react"
import { get, set, del } from "idb-keyval"
import { logError } from "@/app/logger"
import { getDatabaseLazily } from "@/db/lazy"
import { useAuthStore } from "@/stores/useAuthStore"
import { captureSessionEpoch } from "@/stores/sessionEpoch"
import { getConfirmedUserId } from "@/stores/authIdentity"
import { useDebounced } from "./useDebounced"

const KEY_PREFIX = "schedule:notes:v2:"
export interface LessonNote {
  text: string
  updatedAt: number
}
type ScopedNote = { key: string | null; note: LessonNote | null }
type PendingNoteWrite = {
  key: string
  lessonId: string
  owner: string
  snapshot: ScopedNote
  sessionIsCurrent: () => boolean
}
const noteId = (owner: string, lesson: string) => JSON.stringify([owner, lesson])
const selectOwner = getConfirmedUserId

// Serialize each namespace so a late write can be rolled back without deleting
// a newer note. Different accounts never share a persistence key.
const writes = new Map<string, Promise<void>>()
function persistNote(key: string, lesson: string, note: LessonNote | null, owns: () => boolean) {
  const session = captureSessionEpoch()
  const isCurrent = () => session() && owns()
  const pending = (writes.get(key) ?? Promise.resolve()).then(async () => {
    if (!isCurrent()) return
    try {
      const db = await getDatabaseLazily()
      if (isCurrent()) {
        if (note?.text.trim()) {
          const saved = await db.notes.upsert({
            id: key,
            lesson_id: lesson,
            text: note.text,
            updated_at: note.updatedAt,
            is_synced: false,
          })
          if (!isCurrent()) await saved.remove()
        } else {
          const row = await db.notes.findOne(key).exec()
          if (isCurrent() && row) await row.remove()
        }
      }
    } catch {
      // idb-keyval remains available when the optional RxDB runtime is offline.
    }
    if (!isCurrent()) return
    try {
      if (note?.text.trim()) {
        await set(`${KEY_PREFIX}${key}`, note)
        if (!isCurrent()) await del(`${KEY_PREFIX}${key}`)
      } else await del(`${KEY_PREFIX}${key}`)
    } catch (err) {
      logError("[schedule:notes]", err)
    }
  })
  writes.set(key, pending)
  void pending.finally(() => {
    if (writes.get(key) === pending) writes.delete(key)
  })
}

function persistPendingNote(pending: PendingNoteWrite) {
  const owns = () =>
    pending.sessionIsCurrent() && selectOwner(useAuthStore.getState()) === pending.owner
  if (owns()) persistNote(pending.key, pending.lessonId, pending.snapshot.note, owns)
}

export function useLessonNotes(lessonId: string | null | undefined) {
  const owner = useAuthStore(selectOwner)
  const key = owner && lessonId ? noteId(owner, lessonId) : null
  const [state, setState] = useState<ScopedNote>({ key: null, note: null })
  const [loadingKey, setLoadingKey] = useState<string | null>(null)
  const debounced = useDebounced(state, "default")
  const lastSavedRef = useRef<ScopedNote | null>(null)
  const pendingWriteRef = useRef<PendingNoteWrite | null>(null)
  const editRevisionRef = useRef(0)

  useEffect(() => {
    const editRevisionAtStart = editRevisionRef.current
    let active = true
    const owns = () => active && selectOwner(useAuthStore.getState()) === owner
    const pending = pendingWriteRef.current
    if (
      pending &&
      pending.key === key &&
      pending.lessonId === lessonId &&
      pending.owner === owner &&
      pending.sessionIsCurrent() &&
      selectOwner(useAuthStore.getState()) === owner
    ) {
      // A layout-effect edit precedes this passive load; keep the newer edit.
      setState(pending.snapshot)
      lastSavedRef.current = null
      setLoadingKey(null)
      return () => {
        active = false
      }
    }
    setState({ key, note: null })
    lastSavedRef.current = null
    setLoadingKey(key)
    if (!key)
      return () => {
        active = false
      }
    async function load() {
      let loaded: LessonNote | null = null
      try {
        const db = await getDatabaseLazily()
        if (!owns()) return
        const row = await db.notes.findOne(key!).exec()
        if (row) loaded = { text: row.text, updatedAt: row.updated_at }
      } catch {
        /* fall back to IndexedDB */
      }
      if (!owns()) return
      if (!loaded) loaded = (await get<LessonNote>(`${KEY_PREFIX}${key}`).catch(() => null)) ?? null
      if (owns()) {
        if (editRevisionRef.current !== editRevisionAtStart) {
          setLoadingKey(null)
          return
        }
        const next = { key, note: loaded }
        lastSavedRef.current = next
        setState(next)
        setLoadingKey(null)
      }
    }
    void load()
    return () => {
      active = false
    }
  }, [key, lessonId, owner])

  useEffect(() => {
    const effectKey = key
    const effectLessonId = lessonId
    const effectOwner = owner
    return () => {
      const pending = pendingWriteRef.current
      if (
        !pending ||
        pending.key !== effectKey ||
        pending.lessonId !== effectLessonId ||
        pending.owner !== effectOwner
      )
        return
      pendingWriteRef.current = null
      persistPendingNote(pending)
    }
  }, [key, lessonId, owner])

  useEffect(() => {
    if (
      !key ||
      !lessonId ||
      loadingKey === key ||
      debounced.key !== key ||
      debounced === lastSavedRef.current
    )
      return
    lastSavedRef.current = debounced
    const pending = pendingWriteRef.current
    if (pending?.snapshot === debounced) {
      pendingWriteRef.current = null
      persistPendingNote(pending)
    } else {
      persistNote(
        key,
        lessonId,
        debounced.note,
        () => selectOwner(useAuthStore.getState()) === owner
      )
    }
  }, [debounced, key, lessonId, owner, loadingKey])

  const setNote = useCallback(
    (text: string) => {
      if (owner && key && lessonId && selectOwner(useAuthStore.getState()) === owner) {
        const snapshot = { key, note: { text, updatedAt: Date.now() } }
        const previous = pendingWriteRef.current
        if (previous && previous.key !== key) {
          pendingWriteRef.current = null
          persistPendingNote(previous)
        }
        editRevisionRef.current += 1
        pendingWriteRef.current = {
          key,
          lessonId,
          owner,
          snapshot,
          sessionIsCurrent: captureSessionEpoch(),
        }
        setState(snapshot)
      }
    },
    [key, lessonId, owner]
  )

  const clearNote = useCallback(() => {
    if (!key || !lessonId || selectOwner(useAuthStore.getState()) !== owner) return
    editRevisionRef.current += 1
    if (pendingWriteRef.current?.key === key) pendingWriteRef.current = null
    const next = { key, note: null }
    lastSavedRef.current = next
    setState(next)
    persistNote(key, lessonId, null, () => selectOwner(useAuthStore.getState()) === owner)
  }, [key, lessonId, owner])

  const note = state.key === key ? state.note : null
  return {
    note,
    isLoading: key !== null && loadingKey === key,
    setNote,
    clearNote,
    hasNote: !!note?.text.trim(),
  }
}

export function useLessonNotesMap(lessonIds: string[]) {
  const owner = useAuthStore(selectOwner)
  const depKey = JSON.stringify(lessonIds)
  const [state, setState] = useState<{ scope: string; map: Map<string, boolean> }>({
    scope: "",
    map: new Map(),
  })
  const scope = JSON.stringify([owner, depKey])
  useEffect(() => {
    if (!owner || lessonIds.length === 0) return
    let active = true
    const owns = () => active && selectOwner(useAuthStore.getState()) === owner
    async function load() {
      const map = new Map<string, boolean>()
      const ids = lessonIds.map((id) => noteId(owner!, id))
      try {
        const db = await getDatabaseLazily()
        if (!owns()) return
        const rows = await db.notes.find({ selector: { id: { $in: ids } } }).exec()
        rows.forEach((row) => {
          if (row.text?.trim()) map.set(row.lesson_id, true)
        })
      } catch {
        /* fall back to IndexedDB */
      }
      if (!owns()) return
      await Promise.all(
        lessonIds.map(async (id) => {
          if (!map.has(id)) {
            const stored = await get<LessonNote>(`${KEY_PREFIX}${noteId(owner!, id)}`).catch(
              () => null
            )
            map.set(id, !!stored?.text.trim())
          }
        })
      )
      if (owns()) setState({ scope, map })
    }
    void load()
    return () => {
      active = false
    }
  }, [depKey, owner, scope]) // eslint-disable-line react-hooks/exhaustive-deps -- stable serialized lesson IDs
  return state.scope === scope ? state.map : new Map<string, boolean>()
}
