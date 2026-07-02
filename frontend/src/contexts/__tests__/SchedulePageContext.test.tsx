import { renderHook, act } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"

vi.mock("@/components/schedule/scheduleUtils", () => ({
  // Only the Lesson type is used, which is a TS type — no runtime mock needed
}))

import { SchedulePageProvider, useSchedulePage } from "@/contexts/SchedulePageContext"

const wrapper = ({ children }: { children: ReactNode }) => (
  <SchedulePageProvider>{children}</SchedulePageProvider>
)

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => {
  vi.restoreAllMocks()
})

const makeFakeLesson = (overrides: Record<string, unknown> = {}) => ({
  id: "lesson-1",
  weekday: "Monday",
  parity: "both" as const,
  start_time: "09:00",
  end_time: "10:30",
  subject: "Math",
  teacher: "Dr. Smith",
  room: "101",
  lesson_type: "lecture",
  ...overrides,
})

describe("SchedulePageContext", () => {
  describe("useSchedulePage hook", () => {
    it("throws when used outside SchedulePageProvider", () => {
      const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {})

      expect(() => {
        renderHook(() => useSchedulePage())
      }).toThrow(/useSchedulePage must be used within a SchedulePageProvider/)

      errorSpy.mockRestore()
    })

    it("returns expected shape inside SchedulePageProvider", () => {
      const { result } = renderHook(() => useSchedulePage(), { wrapper })

      expect(result.current).toMatchObject({
        activeDialog: null,
        selectedLesson: null,
        openDialog: expect.any(Function),
        closeDialog: expect.any(Function),
        snackbarMessage: null,
        snackbarSeverity: "success",
        showSnackbar: expect.any(Function),
        hideSnackbar: expect.any(Function),
        addDay: null,
        setAddDay: expect.any(Function),
      })
    })
  })

  describe("dialog state", () => {
    it("openDialog sets activeDialog and selectedLesson", () => {
      const { result } = renderHook(() => useSchedulePage(), { wrapper })
      const lesson = makeFakeLesson()

      act(() => {
        result.current.openDialog("details", lesson)
      })

      expect(result.current.activeDialog).toBe("details")
      expect(result.current.selectedLesson).toEqual(lesson)
    })

    it("openDialog without lesson keeps selectedLesson null", () => {
      const { result } = renderHook(() => useSchedulePage(), { wrapper })

      act(() => {
        result.current.openDialog("add")
      })

      expect(result.current.activeDialog).toBe("add")
      expect(result.current.selectedLesson).toBeNull()
    })

    it("openDialog with 'edit' type sets correct dialog", () => {
      const { result } = renderHook(() => useSchedulePage(), { wrapper })
      const lesson = makeFakeLesson({ id: "lesson-2" })

      act(() => {
        result.current.openDialog("edit", lesson)
      })

      expect(result.current.activeDialog).toBe("edit")
      expect(result.current.selectedLesson).toEqual(lesson)
    })

    it("openDialog with null type sets activeDialog to null", () => {
      const { result } = renderHook(() => useSchedulePage(), { wrapper })

      act(() => {
        result.current.openDialog("details", makeFakeLesson())
      })

      act(() => {
        result.current.openDialog(null)
      })

      expect(result.current.activeDialog).toBeNull()
    })

    it("closeDialog resets all state (activeDialog, selectedLesson, addDay)", () => {
      const { result } = renderHook(() => useSchedulePage(), { wrapper })

      act(() => {
        result.current.openDialog("details", makeFakeLesson())
        result.current.setAddDay("Monday")
      })

      expect(result.current.activeDialog).toBe("details")
      expect(result.current.addDay).toBe("Monday")

      act(() => {
        result.current.closeDialog()
      })

      expect(result.current.activeDialog).toBeNull()
      expect(result.current.selectedLesson).toBeNull()
      expect(result.current.addDay).toBeNull()
    })
  })

  describe("snackbar state", () => {
    it("showSnackbar sets message and default 'success' severity", () => {
      const { result } = renderHook(() => useSchedulePage(), { wrapper })

      act(() => {
        result.current.showSnackbar("Lesson saved!")
      })

      expect(result.current.snackbarMessage).toBe("Lesson saved!")
      expect(result.current.snackbarSeverity).toBe("success")
    })

    it("showSnackbar with 'error' severity", () => {
      const { result } = renderHook(() => useSchedulePage(), { wrapper })

      act(() => {
        result.current.showSnackbar("Failed to save", "error")
      })

      expect(result.current.snackbarMessage).toBe("Failed to save")
      expect(result.current.snackbarSeverity).toBe("error")
    })

    it("hideSnackbar clears message", () => {
      const { result } = renderHook(() => useSchedulePage(), { wrapper })

      act(() => {
        result.current.showSnackbar("Saved!")
      })

      expect(result.current.snackbarMessage).toBe("Saved!")

      act(() => {
        result.current.hideSnackbar()
      })

      expect(result.current.snackbarMessage).toBeNull()
    })

    it("hideSnackbar preserves severity for next snackbar", () => {
      const { result } = renderHook(() => useSchedulePage(), { wrapper })

      act(() => {
        result.current.showSnackbar("Error!", "error")
      })

      act(() => {
        result.current.hideSnackbar()
      })

      // Severity stays until next showSnackbar call changes it
      expect(result.current.snackbarSeverity).toBe("error")
    })
  })

  describe("addDay state", () => {
    it("setAddDay updates addDay state", () => {
      const { result } = renderHook(() => useSchedulePage(), { wrapper })

      act(() => {
        result.current.setAddDay("Tuesday")
      })

      expect(result.current.addDay).toBe("Tuesday")
    })

    it("setAddDay with null clears addDay", () => {
      const { result } = renderHook(() => useSchedulePage(), { wrapper })

      act(() => {
        result.current.setAddDay("Wednesday")
      })

      act(() => {
        result.current.setAddDay(null)
      })

      expect(result.current.addDay).toBeNull()
    })
  })
})
