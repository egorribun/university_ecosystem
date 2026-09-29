import type { ChangeEvent, FocusEvent } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { act, renderHook } from "@testing-library/react"
import { AxiosError } from "axios"
import { useDndSettings } from "../useDndSettings"

type MockUser = {
  id: string
  preferences: {
    dnd_enabled: boolean
    dnd_start: string | null
    dnd_end: string | null
  } | null
}

const mocks = vi.hoisted(() => {
  const t = (key: string) => key
  return {
    user: null as MockUser | null,
    setUser: vi.fn(),
    put: vi.fn(),
    t,
    useTranslation: vi.fn((_namespaces: unknown) => ({ t })),
  }
})

vi.mock("react-i18next", () => ({ useTranslation: mocks.useTranslation }))
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: mocks.user, setUser: mocks.setUser }),
}))
vi.mock("@/api/client", () => ({ default: { put: mocks.put } }))

const changeEvent = (value: string) => ({ target: { value } }) as ChangeEvent<HTMLInputElement>
const blurEvent = (value: string) => ({ currentTarget: { value } }) as FocusEvent<HTMLInputElement>

describe("useDndSettings", () => {
  beforeEach(() => {
    mocks.user = {
      id: "user-1",
      preferences: { dnd_enabled: false, dnd_start: null, dnd_end: null },
    }
    mocks.put.mockReset()
    mocks.setUser.mockReset()
    mocks.useTranslation.mockClear()
  })

  const enabledUser = (start: string | null, end: string | null): MockUser => ({
    id: "user-1",
    preferences: { dnd_enabled: true, dnd_start: start, dnd_end: end },
  })

  it("hydrates enabled DND state from server times", () => {
    mocks.user = {
      id: "user-1",
      preferences: { dnd_enabled: true, dnd_start: "21:30:00", dnd_end: "06:15:00" },
    }

    const { result } = renderHook(() => useDndSettings(vi.fn()))

    expect(result.current.dndEnabled).toBe(true)
    expect(result.current.dndStart).toBe("21:30")
    expect(result.current.dndEnd).toBe("06:15")
  })

  it("hydrates enabled defaults when the server omits the time range", () => {
    mocks.user = {
      id: "user-1",
      preferences: { dnd_enabled: true, dnd_start: null, dnd_end: null },
    }

    const { result } = renderHook(() => useDndSettings(vi.fn()))

    expect(result.current.dndEnabled).toBe(true)
    expect(result.current.dndStart).toBe("22:00")
    expect(result.current.dndEnd).toBe("07:00")
  })

  it("ignores time blurs while DND is disabled", () => {
    const { result } = renderHook(() => useDndSettings(vi.fn()))

    act(() => {
      result.current.handleDndStartBlur(blurEvent("20:00"))
      result.current.handleDndEndBlur(blurEvent("06:00"))
    })

    expect(mocks.put).not.toHaveBeenCalled()
  })

  it("enables DND with defaults and persists normalized server values", async () => {
    const setSnackbar = vi.fn()
    const updatedUser = {
      id: "user-1",
      preferences: { dnd_enabled: true, dnd_start: "22:00:00", dnd_end: "07:00:00" },
    }
    mocks.put.mockResolvedValue({ data: updatedUser })
    const { result } = renderHook(() => useDndSettings(setSnackbar))

    await act(async () => {
      result.current.handleDndToggle({} as ChangeEvent<HTMLInputElement>, true)
      await vi.waitFor(() => {
        expect(mocks.put).toHaveBeenCalledWith("/users/me", {
          preferences: { dnd_enabled: true, dnd_start: "22:00:00", dnd_end: "07:00:00" },
        })
      })
    })
    expect(mocks.setUser).toHaveBeenCalledWith(updatedUser)
    expect(setSnackbar).toHaveBeenCalledWith({
      text: "settings:dnd.snackbar.enabled",
      severity: "success",
    })
  })

  it("validates an incomplete enabled range on blur without issuing a write", async () => {
    const setSnackbar = vi.fn()
    mocks.user = {
      id: "user-1",
      preferences: { dnd_enabled: true, dnd_start: "22:00:00", dnd_end: "07:00:00" },
    }
    const { result } = renderHook(() => useDndSettings(setSnackbar))

    act(() => {
      result.current.handleDndStartChange(changeEvent(""))
      result.current.handleDndStartBlur(blurEvent(""))
    })

    await vi.waitFor(() => {
      expect(setSnackbar).toHaveBeenCalledWith({
        text: "settings:dnd.validation.missingRange",
        severity: "warning",
      })
    })
    expect(mocks.put).not.toHaveBeenCalled()
    expect(result.current.dndStart).toBe("22:00")
  })

  it("restores server state and reports the API detail when persistence fails", async () => {
    const setSnackbar = vi.fn()
    mocks.put.mockRejectedValue({
      isAxiosError: true,
      response: { data: { detail: "Policy denied" } },
    })
    const { result } = renderHook(() => useDndSettings(setSnackbar))

    await act(async () => {
      result.current.handleDndToggle({} as ChangeEvent<HTMLInputElement>, true)
      await vi.waitFor(() => {
        expect(setSnackbar).toHaveBeenCalledWith({ text: "Policy denied", severity: "error" })
      })
    })
    expect(result.current.dndEnabled).toBe(false)
  })

  it("disables DND with null server times and reports the disabled state", async () => {
    const setSnackbar = vi.fn()
    mocks.user = {
      id: "user-1",
      preferences: { dnd_enabled: true, dnd_start: "22:00:00", dnd_end: "07:00:00" },
    }
    const updatedUser = {
      id: "user-1",
      preferences: { dnd_enabled: false, dnd_start: null, dnd_end: null },
    }
    mocks.put.mockResolvedValue({ data: updatedUser })
    const { result } = renderHook(() => useDndSettings(setSnackbar))

    await act(async () => {
      result.current.handleDndToggle({} as ChangeEvent<HTMLInputElement>, false)
      await vi.waitFor(() => expect(mocks.put).toHaveBeenCalled())
    })
    expect(mocks.put).toHaveBeenCalledWith("/users/me", {
      preferences: { dnd_enabled: false, dnd_start: null, dnd_end: null },
    })
    expect(setSnackbar).toHaveBeenCalledWith({
      text: "settings:dnd.snackbar.disabled",
      severity: "success",
    })
  })

  it("updates an enabled range and preserves explicit seconds", async () => {
    const setSnackbar = vi.fn()
    mocks.user = {
      id: "user-1",
      preferences: { dnd_enabled: true, dnd_start: "22:00:00", dnd_end: "07:00:00" },
    }
    const updatedUser = {
      id: "user-1",
      preferences: { dnd_enabled: true, dnd_start: "23:45:30", dnd_end: "08:00:00" },
    }
    mocks.put.mockResolvedValue({ data: updatedUser })
    const { result } = renderHook(() => useDndSettings(setSnackbar))

    await act(async () => {
      result.current.handleDndStartChange(changeEvent("23:45:30"))
      result.current.handleDndStartBlur(blurEvent("23:45:30"))
      await vi.waitFor(() => expect(mocks.put).toHaveBeenCalled())
    })
    expect(mocks.put).toHaveBeenCalledWith("/users/me", {
      preferences: { dnd_enabled: true, dnd_start: "23:45:30", dnd_end: "07:00:00" },
    })
    expect(setSnackbar).toHaveBeenCalledWith({
      text: "settings:dnd.snackbar.updated",
      severity: "success",
    })
  })

  it("handles end-time blur and keeps non-standard input values unchanged", async () => {
    const setSnackbar = vi.fn()
    mocks.user = {
      id: "user-1",
      preferences: { dnd_enabled: true, dnd_start: "22:00:00", dnd_end: "07:00:00" },
    }
    mocks.put.mockResolvedValue({
      data: {
        id: "user-1",
        preferences: { dnd_enabled: true, dnd_start: "22:00:00", dnd_end: "invalid" },
      },
    })
    const { result } = renderHook(() => useDndSettings(setSnackbar))

    await act(async () => {
      result.current.handleDndEndChange(changeEvent("invalid"))
      result.current.handleDndEndBlur(blurEvent("invalid"))
      await vi.waitFor(() => expect(mocks.put).toHaveBeenCalled())
    })
    expect(mocks.put).toHaveBeenCalledWith("/users/me", {
      preferences: { dnd_enabled: true, dnd_start: "22:00:00", dnd_end: "invalid" },
    })
  })

  it("validates an empty end-time blur without issuing a write", async () => {
    const setSnackbar = vi.fn()
    mocks.user = {
      id: "user-1",
      preferences: { dnd_enabled: true, dnd_start: "22:00:00", dnd_end: "07:00:00" },
    }
    const { result } = renderHook(() => useDndSettings(setSnackbar))

    act(() => {
      result.current.handleDndEndChange(changeEvent(""))
      result.current.handleDndEndBlur(blurEvent(""))
    })

    await vi.waitFor(() =>
      expect(setSnackbar).toHaveBeenCalledWith({
        text: "settings:dnd.validation.missingRange",
        severity: "warning",
      })
    )
    expect(mocks.put).not.toHaveBeenCalled()
  })

  it("passes missing sibling times through the validation guard", async () => {
    const setSnackbar = vi.fn()
    mocks.user = {
      id: "user-1",
      preferences: { dnd_enabled: true, dnd_start: "22:00:00", dnd_end: "07:00:00" },
    }
    const { result } = renderHook(() => useDndSettings(setSnackbar))

    act(() => {
      result.current.handleDndEndChange(changeEvent(""))
    })
    await vi.waitFor(() => expect(result.current.dndEnd).toBe(""))
    act(() => result.current.handleDndStartBlur(blurEvent("20:00")))
    await vi.waitFor(() => expect(setSnackbar).toHaveBeenCalledTimes(1))

    act(() => {
      result.current.handleDndStartChange(changeEvent(""))
    })
    await vi.waitFor(() => expect(result.current.dndStart).toBe(""))
    act(() => result.current.handleDndEndBlur(blurEvent("06:00")))
    await vi.waitFor(() => expect(setSnackbar).toHaveBeenCalledTimes(2))
    expect(mocks.put).not.toHaveBeenCalled()
  })

  it("skips an unchanged disabled state and ignores duplicate writes while saving", async () => {
    const setSnackbar = vi.fn()
    const { result } = renderHook(() => useDndSettings(setSnackbar))

    act(() => {
      result.current.handleDndToggle({} as ChangeEvent<HTMLInputElement>, false)
    })
    expect(mocks.put).not.toHaveBeenCalled()

    let resolvePut!: (value: unknown) => void
    mocks.put.mockReturnValueOnce(new Promise((resolve) => (resolvePut = resolve)))
    await act(async () => {
      result.current.handleDndToggle({} as ChangeEvent<HTMLInputElement>, true)
      await vi.waitFor(() => expect(mocks.put).toHaveBeenCalledTimes(1))
    })

    act(() => {
      result.current.handleDndToggle({} as ChangeEvent<HTMLInputElement>, false)
    })
    expect(mocks.put).toHaveBeenCalledTimes(1)
    expect(result.current.dndEnabled).toBe(true)
    await act(async () => {
      resolvePut({ data: mocks.user })
      await Promise.resolve()
    })
    expect(result.current.dndSaving).toBe(false)
  })

  it("joins validation-array messages from an Axios error", async () => {
    const setSnackbar = vi.fn()
    const error = new AxiosError("validation")
    error.response = {
      status: 422,
      headers: {},
      data: { detail: [{ msg: "Start is invalid" }, { ignored: true }, { msg: "End is invalid" }] },
      statusText: "",
      config: {} as never,
    }
    mocks.put.mockRejectedValue(error)
    const { result } = renderHook(() => useDndSettings(setSnackbar))

    await act(async () => {
      result.current.handleDndToggle({} as ChangeEvent<HTMLInputElement>, true)
      await vi.waitFor(() =>
        expect(setSnackbar).toHaveBeenCalledWith({
          text: "Start is invalid; End is invalid",
          severity: "error",
        })
      )
      await vi.waitFor(() => expect(result.current.dndSaving).toBe(false))
    })
  })

  it("uses the generic fallback for a non-Axios persistence failure", async () => {
    const setSnackbar = vi.fn()
    mocks.put.mockRejectedValue({ reason: "offline" })
    const { result } = renderHook(() => useDndSettings(setSnackbar))

    await act(async () => {
      result.current.handleDndToggle({} as ChangeEvent<HTMLInputElement>, true)
      await vi.waitFor(() =>
        expect(setSnackbar).toHaveBeenCalledWith({
          text: "settings:dnd.snackbar.updateFailed",
          severity: "error",
        })
      )
    })
  })

  it("uses the generic fallback for an Axios validation array without messages", async () => {
    const setSnackbar = vi.fn()
    const error = new AxiosError("validation")
    error.response = {
      status: 422,
      headers: {},
      data: { detail: [null, { code: "ignored" }] },
      statusText: "",
      config: {} as never,
    }
    mocks.put.mockRejectedValue(error)
    const { result } = renderHook(() => useDndSettings(setSnackbar))

    await act(async () => {
      result.current.handleDndToggle({} as ChangeEvent<HTMLInputElement>, true)
      await vi.waitFor(() =>
        expect(setSnackbar).toHaveBeenCalledWith({
          text: "settings:dnd.snackbar.updateFailed",
          severity: "error",
        })
      )
    })
  })

  it("uses the generic fallback for an unsupported Axios detail shape", async () => {
    const setSnackbar = vi.fn()
    const error = new AxiosError("validation")
    error.response = {
      status: 422,
      headers: {},
      data: { detail: { code: "unsupported" } },
      statusText: "",
      config: {} as never,
    }
    mocks.put.mockRejectedValue(error)
    const { result } = renderHook(() => useDndSettings(setSnackbar))

    await act(async () => {
      result.current.handleDndToggle({} as ChangeEvent<HTMLInputElement>, true)
      await vi.waitFor(() =>
        expect(setSnackbar).toHaveBeenCalledWith({
          text: "settings:dnd.snackbar.updateFailed",
          severity: "error",
        })
      )
    })
  })

  it("loads the settings namespace for its messages", () => {
    renderHook(() => useDndSettings(vi.fn()))

    expect(mocks.useTranslation).toHaveBeenCalledWith(["settings"])
  })

  it("starts disabled with an empty range and keeps a disabled range empty", () => {
    const renders: Array<[boolean, string, string, boolean]> = []
    const { result } = renderHook(() => {
      const state = useDndSettings(vi.fn())
      renders.push([state.dndEnabled, state.dndStart, state.dndEnd, state.dndSaving])
      return state
    })

    expect(renders[0]).toEqual([false, "", "", false])
    expect(result.current.dndEnabled).toBe(false)
    expect(result.current.dndStart).toBe("")
    expect(result.current.dndEnd).toBe("")
  })

  it("hydrates without a signed-in user or stored preferences", () => {
    mocks.user = null
    const { result, rerender } = renderHook(() => useDndSettings(vi.fn()))
    expect(result.current.dndEnabled).toBe(false)

    mocks.user = { id: "user-1", preferences: null }
    rerender()

    expect(result.current.dndEnabled).toBe(false)
    expect(result.current.dndStart).toBe("")
  })

  it("shows the default for a stored time without a two-digit hour", () => {
    mocks.user = enabledUser("9:30:00", "6:15:00")

    const { result } = renderHook(() => useDndSettings(vi.fn()))

    expect(result.current.dndStart).toBe("22:00")
    expect(result.current.dndEnd).toBe("07:00")
  })

  it("re-syncs the range when the signed-in user changes", () => {
    const { result, rerender } = renderHook(() => useDndSettings(vi.fn()))
    expect(result.current.dndEnabled).toBe(false)

    mocks.user = enabledUser("23:00:00", "05:30:00")
    rerender()

    expect(result.current.dndEnabled).toBe(true)
    expect(result.current.dndStart).toBe("23:00")
    expect(result.current.dndEnd).toBe("05:30")
  })

  it.each([
    ["without a signed-in user", null],
    ["without stored preferences", { id: "user-1", preferences: null }],
  ])("enables DND %s", async (_label, user) => {
    const setSnackbar = vi.fn()
    mocks.user = user
    mocks.put.mockResolvedValue({ data: enabledUser("22:00:00", "07:00:00") })
    const { result } = renderHook(() => useDndSettings(setSnackbar))

    await act(async () => {
      result.current.handleDndToggle({} as ChangeEvent<HTMLInputElement>, true)
      await vi.waitFor(() => expect(setSnackbar).toHaveBeenCalled())
    })
    expect(mocks.put).toHaveBeenCalledWith("/users/me", {
      preferences: { dnd_enabled: true, dnd_start: "22:00:00", dnd_end: "07:00:00" },
    })
    expect(setSnackbar).toHaveBeenCalledWith({
      text: "settings:dnd.snackbar.enabled",
      severity: "success",
    })
  })

  it("enables DND with an edited start time and shows the range the server stored", async () => {
    const setSnackbar = vi.fn()
    mocks.put.mockResolvedValue({ data: enabledUser("20:00:00", "06:30:00") })
    const { result } = renderHook(() => useDndSettings(setSnackbar))

    act(() => result.current.handleDndStartChange(changeEvent("20:00")))
    await act(async () => {
      result.current.handleDndToggle({} as ChangeEvent<HTMLInputElement>, true)
      await vi.waitFor(() => expect(setSnackbar).toHaveBeenCalled())
    })

    expect(mocks.put).toHaveBeenCalledWith("/users/me", {
      preferences: { dnd_enabled: true, dnd_start: "20:00:00", dnd_end: "07:00:00" },
    })
    expect(result.current.dndStart).toBe("20:00")
    expect(result.current.dndEnd).toBe("06:30")
  })

  it("shows the enabled range while the write is pending", async () => {
    let resolvePut!: (value: unknown) => void
    mocks.put.mockReturnValue(new Promise((resolve) => (resolvePut = resolve)))
    const { result } = renderHook(() => useDndSettings(vi.fn()))

    act(() => result.current.handleDndToggle({} as ChangeEvent<HTMLInputElement>, true))

    expect(result.current.dndEnabled).toBe(true)
    expect(result.current.dndStart).toBe("22:00")
    expect(result.current.dndEnd).toBe("07:00")
    expect(result.current.dndSaving).toBe(true)
    await act(async () => {
      resolvePut({ data: enabledUser("22:00:00", "07:00:00") })
      await Promise.resolve()
    })
    expect(result.current.dndSaving).toBe(false)
  })

  it("keeps the range visible while disabling is pending", async () => {
    mocks.user = enabledUser("21:00:00", "06:00:00")
    let resolvePut!: (value: unknown) => void
    mocks.put.mockReturnValue(new Promise((resolve) => (resolvePut = resolve)))
    const { result } = renderHook(() => useDndSettings(vi.fn()))

    act(() => result.current.handleDndToggle({} as ChangeEvent<HTMLInputElement>, false))

    expect(result.current.dndEnabled).toBe(false)
    expect(result.current.dndStart).toBe("21:00")
    expect(result.current.dndEnd).toBe("06:00")
    await act(async () => {
      resolvePut({ data: { id: "user-1", preferences: null } })
      await Promise.resolve()
    })
    expect(result.current.dndStart).toBe("")
  })

  it("skips an unchanged enabled range and shows the trimmed times", () => {
    const setSnackbar = vi.fn()
    mocks.user = enabledUser("22:00:00", "07:00:00")
    const { result } = renderHook(() => useDndSettings(setSnackbar))

    act(() => {
      result.current.handleDndStartChange(changeEvent(" 22:00 "))
      result.current.handleDndStartBlur(blurEvent(" 22:00 "))
    })
    act(() => {
      result.current.handleDndEndChange(changeEvent(" 07:00 "))
      result.current.handleDndEndBlur(blurEvent(" 07:00 "))
    })

    expect(result.current.dndStart).toBe("22:00")
    expect(result.current.dndEnd).toBe("07:00")
    expect(mocks.put).not.toHaveBeenCalled()
    expect(setSnackbar).not.toHaveBeenCalled()
  })

  it.each([
    ["start", "22:00:00", null, "handleDndStartChange", "handleDndStartBlur"],
    ["end", null, "07:00:00", "handleDndEndChange", "handleDndEndBlur"],
  ] as const)(
    "requires a %s time the server never stored",
    async (_label, start, end, change, blur) => {
      const setSnackbar = vi.fn()
      mocks.user = enabledUser(start, end)
      const { result } = renderHook(() => useDndSettings(setSnackbar))

      act(() => {
        result.current[change](changeEvent(""))
        result.current[blur](blurEvent(""))
      })

      await vi.waitFor(() =>
        expect(setSnackbar).toHaveBeenCalledWith({
          text: "settings:dnd.validation.missingRange",
          severity: "warning",
        })
      )
      expect(mocks.put).not.toHaveBeenCalled()
    }
  )

  it("trims the unsaved sibling time before persisting a blur", async () => {
    mocks.user = enabledUser("22:00:00", "07:00:00")
    mocks.put.mockResolvedValue({ data: enabledUser("21:00:00", "06:00:00") })
    const { result } = renderHook(() => useDndSettings(vi.fn()))

    act(() => result.current.handleDndStartChange(changeEvent(" 21:00 ")))
    await act(async () => {
      result.current.handleDndEndBlur(blurEvent("06:00"))
      await vi.waitFor(() => expect(mocks.put).toHaveBeenCalledTimes(1))
    })
    expect(mocks.put).toHaveBeenLastCalledWith("/users/me", {
      preferences: { dnd_enabled: true, dnd_start: "21:00:00", dnd_end: "06:00:00" },
    })
    await vi.waitFor(() => expect(result.current.dndSaving).toBe(false))

    act(() => result.current.handleDndEndChange(changeEvent(" 05:00 ")))
    await act(async () => {
      result.current.handleDndStartBlur(blurEvent("20:00"))
      await vi.waitFor(() => expect(mocks.put).toHaveBeenCalledTimes(2))
    })
    expect(mocks.put).toHaveBeenLastCalledWith("/users/me", {
      preferences: { dnd_enabled: true, dnd_start: "20:00:00", dnd_end: "05:00:00" },
    })
  })

  it("ignores time blurs while a write is pending", async () => {
    mocks.user = enabledUser("22:00:00", "07:00:00")
    let resolvePut!: (value: unknown) => void
    mocks.put.mockReturnValueOnce(new Promise((resolve) => (resolvePut = resolve)))
    const { result } = renderHook(() => useDndSettings(vi.fn()))

    act(() => result.current.handleDndStartBlur(blurEvent("23:00")))
    act(() => {
      result.current.handleDndStartBlur(blurEvent("20:00"))
      result.current.handleDndEndBlur(blurEvent("06:00"))
    })

    expect(mocks.put).toHaveBeenCalledTimes(1)
    expect(result.current.dndStart).toBe("23:00")
    expect(result.current.dndEnd).toBe("07:00")
    await act(async () => {
      resolvePut({ data: enabledUser("23:00:00", "07:00:00") })
      await Promise.resolve()
    })
  })

  it("does not surface the detail of a non-Axios failure", async () => {
    const setSnackbar = vi.fn()
    mocks.put.mockRejectedValue({ response: { data: { detail: "Internal detail" } } })
    const { result } = renderHook(() => useDndSettings(setSnackbar))

    await act(async () => {
      result.current.handleDndToggle({} as ChangeEvent<HTMLInputElement>, true)
      await vi.waitFor(() =>
        expect(setSnackbar).toHaveBeenCalledWith({
          text: "settings:dnd.snackbar.updateFailed",
          severity: "error",
        })
      )
    })
  })

  it("uses the generic fallback for an Axios failure without a response", async () => {
    const setSnackbar = vi.fn()
    mocks.put.mockRejectedValue(new AxiosError("Network Error"))
    const { result } = renderHook(() => useDndSettings(setSnackbar))

    await act(async () => {
      result.current.handleDndToggle({} as ChangeEvent<HTMLInputElement>, true)
      await vi.waitFor(() =>
        expect(setSnackbar).toHaveBeenCalledWith({
          text: "settings:dnd.snackbar.updateFailed",
          severity: "error",
        })
      )
    })
  })

  it("skips non-object entries of an Axios validation array", async () => {
    const setSnackbar = vi.fn()
    const error = new AxiosError("validation")
    error.response = {
      status: 422,
      headers: {},
      data: { detail: ["plain text", { msg: "End is invalid" }] },
      statusText: "",
      config: {} as never,
    }
    mocks.put.mockRejectedValue(error)
    const { result } = renderHook(() => useDndSettings(setSnackbar))

    await act(async () => {
      result.current.handleDndToggle({} as ChangeEvent<HTMLInputElement>, true)
      await vi.waitFor(() =>
        expect(setSnackbar).toHaveBeenCalledWith({ text: "End is invalid", severity: "error" })
      )
    })
  })
})
