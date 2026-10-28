import "fake-indexeddb/auto"
import {
  act,
  cleanup,
  fireEvent,
  render,
  renderHook,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { clear, get, set } from "idb-keyval"
import { useState } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { invalidateSessionEpoch } from "@/stores/sessionEpoch"
import { useAuthStore } from "@/stores/useAuthStore"
import { useLessonNotes, useLessonNotesMap, type LessonNote } from "../useLessonNotes"

const database = vi.hoisted(() => ({ open: vi.fn() }))
vi.mock("@/db/lazy", () => ({ getDatabaseLazily: database.open }))

const storageKey = (lesson: string, owner = "user-a") =>
  `schedule:notes:v2:${JSON.stringify([owner, lesson])}`

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

function Editor({ lesson }: { lesson: string }) {
  const { note, setNote, isLoading } = useLessonNotes(lesson)
  return (
    <section>
      <output data-testid="loading">{String(isLoading)}</output>
      <textarea
        aria-label="Lesson note"
        value={note?.text ?? ""}
        onChange={(event) => setNote(event.target.value)}
      />
    </section>
  )
}

// The production Schedule page currently has no useLessonNotes editor. This
// harness exercises the hook's real React mount, key changes and cleanup.
function EditorPage({ initialLesson }: { initialLesson: string }) {
  const [lesson, setLesson] = useState<string | null>(initialLesson)
  return (
    <>
      <button onClick={() => setLesson(null)}>Leave editor</button>
      <button onClick={() => setLesson(initialLesson)}>Open first lesson</button>
      <button onClick={() => setLesson("lesson-b")}>Open second lesson</button>
      {lesson && <Editor lesson={lesson} />}
    </>
  )
}

function TwoEditorsPage() {
  const [firstOpen, setFirstOpen] = useState(true)
  const [secondOpen, setSecondOpen] = useState(false)
  return (
    <>
      <button onClick={() => setFirstOpen(false)}>Close first editor</button>
      <button onClick={() => setSecondOpen(true)}>Open second editor</button>
      {firstOpen && (
        <div data-testid="first-editor">
          <Editor lesson="queued-reopen" />
        </div>
      )}
      {secondOpen && (
        <div data-testid="second-editor">
          <Editor lesson="queued-reopen" />
        </div>
      )}
    </>
  )
}

let previousAuthState: ReturnType<typeof useAuthStore.getState>

beforeEach(async () => {
  await clear()
  previousAuthState = useAuthStore.getState()
  useAuthStore.setState({
    user: { id: "user-a" } as NonNullable<ReturnType<typeof useAuthStore.getState>["user"]>,
    loading: false,
  })
  database.open.mockReset()
  database.open.mockRejectedValue(new Error("RxDB unavailable"))
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  useAuthStore.setState(previousAuthState, true)
})

describe("lesson notes React lifecycle with IndexedDB", () => {
  it("reloads note indicators after discarding a previous session epoch", async () => {
    const reading = deferred<Array<{ lesson_id: string; text: string }>>()
    const freshReading = deferred<Array<{ lesson_id: string; text: string }>>()
    const find = vi
      .fn()
      .mockImplementationOnce(() => ({ exec: () => reading.promise }))
      .mockImplementationOnce(() => ({ exec: () => freshReading.promise }))
    database.open.mockResolvedValue({ notes: { find } })

    try {
      const { result } = renderHook(() => useLessonNotesMap(["indicator-epoch"]))
      await waitFor(() => expect(find).toHaveBeenCalledOnce())
      act(() => invalidateSessionEpoch())
      await act(async () => {
        reading.resolve([{ lesson_id: "indicator-epoch", text: "old note" }])
        await reading.promise
      })
      await waitFor(() => expect(find).toHaveBeenCalledTimes(2))
      expect(result.current.size).toBe(0)
      await act(async () => {
        freshReading.resolve([])
        await freshReading.promise
      })
      await waitFor(() => expect(result.current.get("indicator-epoch")).toBe(false))
    } finally {
      cleanup()
      reading.resolve([])
      freshReading.resolve([])
      await Promise.all([reading.promise, freshReading.promise])
    }
  })

  it("preserves a stored note when the initial load outlasts the debounce", async () => {
    await set(storageKey("lesson-a"), { text: "stored before loading", updatedAt: 1 })
    const opening = deferred<unknown>()
    database.open.mockImplementationOnce(() => opening.promise)

    try {
      vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] })
      render(<EditorPage initialLesson="lesson-a" />)
      await act(() => vi.advanceTimersByTimeAsync(400))
      expect(screen.getByTestId("loading")).toHaveTextContent("true")
      vi.useRealTimers()
      await act(async () => {
        opening.resolve({})
        await opening.promise
      })
      await waitFor(() =>
        expect(screen.getByLabelText("Lesson note")).toHaveValue("stored before loading")
      )
      fireEvent.click(screen.getByRole("button", { name: "Leave editor" }))
      expect(await get<LessonNote>(storageKey("lesson-a"))).toEqual({
        text: "stored before loading",
        updatedAt: 1,
      })
    } finally {
      vi.useRealTimers()
      opening.resolve({})
    }
  })

  it("flushes an edit on leaving and loads it when the editor is reopened", async () => {
    await set(storageKey("lesson-a"), { text: "old note", updatedAt: 1 })
    render(<EditorPage initialLesson="lesson-a" />)
    const input = screen.getByLabelText("Lesson note")
    await waitFor(() => expect(input).toHaveValue("old note"))

    fireEvent.change(input, { target: { value: "edited before leaving" } })
    fireEvent.click(screen.getByRole("button", { name: "Leave editor" }))
    expect(screen.queryByLabelText("Lesson note")).not.toBeInTheDocument()
    await waitFor(async () => {
      expect(await get<LessonNote>(storageKey("lesson-a"))).toEqual({
        text: "edited before leaving",
        updatedAt: expect.any(Number),
      })
    })

    fireEvent.click(screen.getByRole("button", { name: "Open first lesson" }))
    await waitFor(() =>
      expect(screen.getByLabelText("Lesson note")).toHaveValue("edited before leaving")
    )
  })

  it("waits for a pending flush before reopening the same lesson", async () => {
    let stored = { text: "old note", updated_at: 1 }
    const db = {
      notes: {
        findOne: () => ({ exec: async () => stored }),
        upsert: vi.fn(async (note: { text: string; updated_at: number }) => {
          stored = { text: note.text, updated_at: note.updated_at }
          return { remove: async () => {} }
        }),
      },
    }
    database.open.mockResolvedValue(db)
    const opening = deferred<unknown>()

    try {
      render(<EditorPage initialLesson="reopen-pending" />)
      await waitFor(() => expect(screen.getByLabelText("Lesson note")).toHaveValue("old note"))
      database.open.mockImplementationOnce(() => opening.promise)
      fireEvent.change(screen.getByLabelText("Lesson note"), { target: { value: "new note" } })
      fireEvent.click(screen.getByRole("button", { name: "Leave editor" }))
      await waitFor(() => expect(database.open).toHaveBeenCalledTimes(2))

      fireEvent.click(screen.getByRole("button", { name: "Open first lesson" }))
      await act(async () => {
        await Promise.resolve()
        await Promise.resolve()
        await Promise.resolve()
      })
      expect(screen.getByTestId("loading")).toHaveTextContent("true")
      expect(screen.getByLabelText("Lesson note")).toHaveValue("")

      await act(async () => {
        opening.resolve(db)
        await opening.promise
      })
      await waitFor(() => expect(screen.getByLabelText("Lesson note")).toHaveValue("new note"))
      fireEvent.change(screen.getByLabelText("Lesson note"), { target: { value: "new note plus" } })
      fireEvent.click(screen.getByRole("button", { name: "Leave editor" }))
      await waitFor(async () => {
        expect(await get<LessonNote>(storageKey("reopen-pending"))).toEqual({
          text: "new note plus",
          updatedAt: expect.any(Number),
        })
      })
    } finally {
      cleanup()
      await act(async () => {
        opening.resolve(db)
        await opening.promise
        await Promise.resolve()
        await Promise.resolve()
        await get(storageKey("reopen-pending"))
      })
    }
  })

  it("also waits for a newer write queued while a reopened editor is loading", async () => {
    let stored = { text: "old note", updated_at: 1 }
    const firstWrite = deferred<void>()
    const secondWrite = deferred<void>()
    const upsert = vi.fn(async (note: { text: string; updated_at: number }) => {
      if (note.text === "first edit") await firstWrite.promise
      if (note.text === "latest edit") await secondWrite.promise
      stored = { text: note.text, updated_at: note.updated_at }
      return { remove: async () => {} }
    })
    database.open.mockResolvedValue({
      notes: { findOne: () => ({ exec: async () => stored }), upsert },
    })

    try {
      render(<TwoEditorsPage />)
      const first = within(screen.getByTestId("first-editor"))
      await waitFor(() => expect(first.getByLabelText("Lesson note")).toHaveValue("old note"))
      vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] })
      fireEvent.change(first.getByLabelText("Lesson note"), { target: { value: "first edit" } })
      await act(() => vi.advanceTimersByTimeAsync(300))
      vi.useRealTimers()
      await waitFor(() => expect(upsert).toHaveBeenCalledTimes(1))

      fireEvent.click(screen.getByRole("button", { name: "Open second editor" }))
      const second = within(screen.getByTestId("second-editor"))
      expect(second.getByTestId("loading")).toHaveTextContent("true")
      fireEvent.change(first.getByLabelText("Lesson note"), { target: { value: "latest edit" } })
      fireEvent.click(screen.getByRole("button", { name: "Close first editor" }))
      await act(async () => {
        firstWrite.resolve()
        await firstWrite.promise
      })
      await waitFor(() => expect(upsert).toHaveBeenCalledTimes(2))
      expect(second.getByTestId("loading")).toHaveTextContent("true")
      expect(second.getByLabelText("Lesson note")).toHaveValue("")

      await act(async () => {
        secondWrite.resolve()
        await secondWrite.promise
      })
      await waitFor(() => expect(second.getByLabelText("Lesson note")).toHaveValue("latest edit"))
      expect(await get<LessonNote>(storageKey("queued-reopen"))).toEqual({
        text: "latest edit",
        updatedAt: expect.any(Number),
      })
    } finally {
      cleanup()
      vi.useRealTimers()
      await act(async () => {
        firstWrite.resolve()
        secondWrite.resolve()
        await Promise.all([firstWrite.promise, secondWrite.promise])
      })
    }
  })

  it("does not make a different account wait for an earlier account's flush", async () => {
    await set(storageKey("reopen-owner"), { text: "first account", updatedAt: 1 })
    await set(storageKey("reopen-owner", "user-b"), { text: "second account", updatedAt: 2 })
    const opening = deferred<unknown>()
    const upsert = vi.fn()

    try {
      render(<EditorPage initialLesson="reopen-owner" />)
      await waitFor(() => expect(screen.getByLabelText("Lesson note")).toHaveValue("first account"))
      database.open.mockImplementationOnce(() => opening.promise)
      fireEvent.change(screen.getByLabelText("Lesson note"), { target: { value: "pending first" } })
      fireEvent.click(screen.getByRole("button", { name: "Leave editor" }))
      await waitFor(() => expect(database.open).toHaveBeenCalledTimes(2))

      act(() =>
        useAuthStore.setState({
          user: { id: "user-b" } as NonNullable<ReturnType<typeof useAuthStore.getState>["user"]>,
        })
      )
      fireEvent.click(screen.getByRole("button", { name: "Open first lesson" }))
      await waitFor(() =>
        expect(screen.getByLabelText("Lesson note")).toHaveValue("second account")
      )
      await act(async () => {
        opening.resolve({ notes: { upsert } })
        await opening.promise
        await Promise.resolve()
      })
      expect(upsert).not.toHaveBeenCalled()
      expect(await get<LessonNote>(storageKey("reopen-owner"))).toEqual({
        text: "first account",
        updatedAt: 1,
      })
      expect(screen.getByLabelText("Lesson note")).toHaveValue("second account")
    } finally {
      cleanup()
      await act(async () => {
        opening.resolve({ notes: { upsert } })
        await opening.promise
      })
    }
  })

  it("discards an old-session pending write and reloads after same-owner rotation", async () => {
    await set(storageKey("reopen-epoch"), { text: "old account note", updatedAt: 1 })
    const writing = deferred<unknown>()
    const reading = deferred<unknown>()
    const db = {
      notes: {
        findOne: () => ({ exec: async () => ({ text: "old account note", updated_at: 1 }) }),
      },
    }

    try {
      render(<EditorPage initialLesson="reopen-epoch" />)
      await waitFor(() =>
        expect(screen.getByLabelText("Lesson note")).toHaveValue("old account note")
      )
      database.open.mockImplementationOnce(() => writing.promise)
      database.open.mockImplementationOnce(() => reading.promise)
      fireEvent.change(screen.getByLabelText("Lesson note"), { target: { value: "stale edit" } })
      fireEvent.click(screen.getByRole("button", { name: "Leave editor" }))
      await waitFor(() => expect(database.open).toHaveBeenCalledTimes(2))
      fireEvent.click(screen.getByRole("button", { name: "Open first lesson" }))
      act(() => invalidateSessionEpoch())

      await act(async () => {
        writing.resolve({})
        reading.resolve(db)
        await Promise.all([writing.promise, reading.promise])
        await Promise.resolve()
        await Promise.resolve()
      })
      await waitFor(() =>
        expect(screen.getByLabelText("Lesson note")).toHaveValue("old account note")
      )
      expect(await get<LessonNote>(storageKey("reopen-epoch"))).toEqual({
        text: "old account note",
        updatedAt: 1,
      })
    } finally {
      cleanup()
      await act(async () => {
        writing.resolve({})
        reading.resolve(db)
        await Promise.all([writing.promise, reading.promise])
      })
    }
  })

  it("recovers on the same mount after a stale read and saves a new-session edit", async () => {
    await set(storageKey("same-mount-recovery"), { text: "saved session note", updatedAt: 1 })
    const reading = deferred<unknown>()
    database.open.mockImplementationOnce(() => reading.promise)

    try {
      render(<EditorPage initialLesson="same-mount-recovery" />)
      expect(screen.getByTestId("loading")).toHaveTextContent("true")
      act(() => invalidateSessionEpoch())
      await act(async () => {
        reading.resolve({})
        await reading.promise
      })
      await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("false"))
      expect(screen.getByLabelText("Lesson note")).toHaveValue("saved session note")

      vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] })
      fireEvent.change(screen.getByLabelText("Lesson note"), {
        target: { value: "new session edit" },
      })
      await act(() => vi.advanceTimersByTimeAsync(300))
      vi.useRealTimers()
      await waitFor(async () => {
        expect(await get<LessonNote>(storageKey("same-mount-recovery"))).toEqual({
          text: "new session edit",
          updatedAt: expect.any(Number),
        })
      })
      expect(screen.getByLabelText("Lesson note")).toHaveValue("new session edit")
    } finally {
      cleanup()
      vi.useRealTimers()
      reading.resolve({})
      await reading.promise
    }
  })

  it("restores the stored note instead of showing an old-session draft after rotation", async () => {
    await set(storageKey("old-session-draft"), { text: "stored note", updatedAt: 1 })
    const reading = deferred<unknown>()
    database.open.mockImplementationOnce(() => reading.promise)
    try {
      render(<EditorPage initialLesson="old-session-draft" />)
      fireEvent.change(screen.getByLabelText("Lesson note"), { target: { value: "stale draft" } })
      act(() => invalidateSessionEpoch())
      await act(async () => {
        reading.resolve({})
        await reading.promise
      })
      await waitFor(() => expect(screen.getByLabelText("Lesson note")).toHaveValue("stored note"))
      expect(await get<LessonNote>(storageKey("old-session-draft"))).toEqual({
        text: "stored note",
        updatedAt: 1,
      })
    } finally {
      cleanup()
      reading.resolve({})
      await reading.promise
    }
  })

  it("preserves a new-session edit made while an old-session read is pending", async () => {
    await set(storageKey("new-session-draft"), { text: "stored note", updatedAt: 1 })
    const reading = deferred<unknown>()
    database.open.mockImplementationOnce(() => reading.promise)
    try {
      render(<EditorPage initialLesson="new-session-draft" />)
      act(() => invalidateSessionEpoch())
      fireEvent.change(screen.getByLabelText("Lesson note"), { target: { value: "current draft" } })
      await act(async () => {
        reading.resolve({})
        await reading.promise
      })
      await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("false"))
      expect(screen.getByLabelText("Lesson note")).toHaveValue("current draft")
      vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] })
      await act(() => vi.advanceTimersByTimeAsync(300))
      vi.useRealTimers()
      await waitFor(async () => {
        expect(await get<LessonNote>(storageKey("new-session-draft"))).toEqual({
          text: "current draft",
          updatedAt: expect.any(Number),
        })
      })
    } finally {
      cleanup()
      vi.useRealTimers()
      reading.resolve({})
      await reading.promise
    }
  })

  it("restores a note when an old-session clear is cancelled during loading", async () => {
    await set(storageKey("old-session-clear"), { text: "stored note", updatedAt: 1 })
    const reading = deferred<unknown>()
    database.open.mockImplementationOnce(() => reading.promise)
    try {
      const { result } = renderHook(() => useLessonNotes("old-session-clear"))
      act(() => result.current.clearNote())
      act(() => invalidateSessionEpoch())
      await act(async () => {
        reading.resolve({})
        await reading.promise
      })
      await waitFor(() => expect(result.current.note?.text).toBe("stored note"))
      expect(await get<LessonNote>(storageKey("old-session-clear"))).toEqual({
        text: "stored note",
        updatedAt: 1,
      })
    } finally {
      cleanup()
      reading.resolve({})
      await reading.promise
    }
  })

  it("keeps a new-session clear made while an old-session read is pending", async () => {
    await set(storageKey("new-session-clear"), { text: "stored note", updatedAt: 1 })
    const reading = deferred<unknown>()
    database.open.mockImplementationOnce(() => reading.promise)
    try {
      const { result } = renderHook(() => useLessonNotes("new-session-clear"))
      act(() => invalidateSessionEpoch())
      act(() => result.current.clearNote())
      await waitFor(async () => {
        expect(await get<LessonNote>(storageKey("new-session-clear"))).toBeUndefined()
      })
      await act(async () => {
        reading.resolve({})
        await reading.promise
      })
      await waitFor(() => expect(result.current.isLoading).toBe(false))
      expect(result.current.note).toBeNull()
      expect(await get<LessonNote>(storageKey("new-session-clear"))).toBeUndefined()
    } finally {
      cleanup()
      reading.resolve({})
      await reading.promise
    }
  })

  it("saves an edit made before loading when switching lessons", async () => {
    await set(storageKey("lesson-a"), { text: "old first lesson", updatedAt: 1 })
    await set(storageKey("lesson-b"), { text: "second lesson", updatedAt: 2 })
    const opening = deferred<unknown>()
    database.open.mockImplementationOnce(() => opening.promise)

    try {
      render(<EditorPage initialLesson="lesson-a" />)
      await waitFor(() => expect(database.open).toHaveBeenCalledTimes(1))
      expect(screen.getByTestId("loading")).toHaveTextContent("true")
      fireEvent.change(screen.getByLabelText("Lesson note"), {
        target: { value: "new first lesson" },
      })
      fireEvent.click(screen.getByRole("button", { name: "Open second lesson" }))

      await waitFor(() => expect(screen.getByLabelText("Lesson note")).toHaveValue("second lesson"))
      await waitFor(async () => {
        expect(await get<LessonNote>(storageKey("lesson-a"))).toEqual({
          text: "new first lesson",
          updatedAt: expect.any(Number),
        })
      })
      await act(async () => {
        opening.resolve({})
        await opening.promise
      })
      expect(screen.getByLabelText("Lesson note")).toHaveValue("second lesson")
      expect(await get<LessonNote>(storageKey("lesson-b"))).toEqual({
        text: "second lesson",
        updatedAt: 2,
      })
    } finally {
      opening.resolve({})
    }
  })

  it("persists the latest edit after an earlier write is in flight and the editor closes", async () => {
    const finishFirstWrite = deferred<{ remove: () => Promise<void> }>()
    const upsert = vi
      .fn()
      .mockImplementationOnce(() => finishFirstWrite.promise)
      .mockResolvedValue({ remove: async () => {} })
    const findOne = () => ({ exec: async () => null })
    database.open.mockResolvedValue({ notes: { findOne, upsert } })

    try {
      render(<EditorPage initialLesson="lesson-a" />)
      await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("false"))
      vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] })
      fireEvent.change(screen.getByLabelText("Lesson note"), { target: { value: "first edit" } })
      await act(() => vi.advanceTimersByTimeAsync(300))
      vi.useRealTimers()
      await waitFor(() => expect(upsert).toHaveBeenCalledTimes(1))
      fireEvent.change(screen.getByLabelText("Lesson note"), { target: { value: "latest edit" } })
      fireEvent.click(screen.getByRole("button", { name: "Leave editor" }))
      expect(upsert).toHaveBeenCalledTimes(1)

      await act(async () => {
        finishFirstWrite.resolve({ remove: async () => {} })
        await finishFirstWrite.promise
      })
      await waitFor(async () => {
        expect(await get<LessonNote>(storageKey("lesson-a"))).toEqual({
          text: "latest edit",
          updatedAt: expect.any(Number),
        })
      })
      expect(upsert).toHaveBeenCalledTimes(2)
      expect(upsert.mock.calls.map(([note]) => note.text)).toEqual(["first edit", "latest edit"])
      fireEvent.click(screen.getByRole("button", { name: "Open first lesson" }))
      await waitFor(() => expect(screen.getByLabelText("Lesson note")).toHaveValue("latest edit"))
    } finally {
      vi.useRealTimers()
      finishFirstWrite.resolve({ remove: async () => {} })
    }
  })

  it("preserves the new account's stored note when its load outlasts the debounce", async () => {
    await set(storageKey("lesson-a"), { text: "private first account", updatedAt: 1 })
    await set(storageKey("lesson-a", "user-b"), { text: "second account", updatedAt: 2 })
    const opening = deferred<unknown>()
    try {
      render(<EditorPage initialLesson="lesson-a" />)
      await waitFor(() =>
        expect(screen.getByLabelText("Lesson note")).toHaveValue("private first account")
      )
      database.open.mockImplementationOnce(() => opening.promise)
      vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] })
      fireEvent.change(screen.getByLabelText("Lesson note"), {
        target: { value: "pending first account" },
      })

      act(() =>
        useAuthStore.setState({
          user: { id: "user-b" } as NonNullable<ReturnType<typeof useAuthStore.getState>["user"]>,
        })
      )
      await act(() => vi.advanceTimersByTimeAsync(400))
      expect(screen.getByTestId("loading")).toHaveTextContent("true")
      vi.useRealTimers()
      await act(async () => {
        opening.resolve({})
        await opening.promise
      })
      await waitFor(() =>
        expect(screen.getByLabelText("Lesson note")).toHaveValue("second account")
      )
      fireEvent.click(screen.getByRole("button", { name: "Leave editor" }))
      expect(await get<LessonNote>(storageKey("lesson-a"))).toEqual({
        text: "private first account",
        updatedAt: 1,
      })
      expect(await get<LessonNote>(storageKey("lesson-a", "user-b"))).toEqual({
        text: "second account",
        updatedAt: 2,
      })
    } finally {
      vi.useRealTimers()
      opening.resolve({})
    }
  })
})
