import type { ChangeEvent, FocusEvent } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { act, renderHook } from "@testing-library/react"
import { AxiosError } from "axios"
import { useDndSettings } from "../useDndSettings"

const mocks = vi.hoisted(() => ({
  user: {
    id: "user-1",
    preferences: {
      dnd_enabled: false,
      dnd_start: null as string | null,
      dnd_end: null as string | null,
    },
  },
  setUser: vi.fn(),
  put: vi.fn(),
  t: (key: string) => key,
}))

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: mocks.t }) }))
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
  })

  it("hydrates enabled DND state from server times", () => {
    mocks.user = {
      ...mocks.user,
      preferences: { dnd_enabled: true, dnd_start: "21:30:00", dnd_end: "06:15:00" },
    }

    const { result } = renderHook(() => useDndSettings(vi.fn()))

    expect(result.current.dndEnabled).toBe(true)
    expect(result.current.dndStart).toBe("21:30")
    expect(result.current.dndEnd).toBe("06:15")
  })

  it("hydrates enabled defaults when the server omits the time range", () => {
    mocks.user = {
      ...mocks.user,
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
      ...mocks.user,
      preferences: { dnd_enabled: true, dnd_start: "22:00:00", dnd_end: "07:00:00" },
    }
    mocks.put.mockResolvedValue({ data: updatedUser })
    const { result } = renderHook(() => useDndSettings(setSnackbar))

    act(() => {
      result.current.handleDndToggle({} as ChangeEvent<HTMLInputElement>, true)
    })

    await vi.waitFor(() => {
      expect(mocks.put).toHaveBeenCalledWith("/users/me", {
        preferences: { dnd_enabled: true, dnd_start: "22:00:00", dnd_end: "07:00:00" },
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
      ...mocks.user,
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

    act(() => {
      result.current.handleDndToggle({} as ChangeEvent<HTMLInputElement>, true)
    })

    await vi.waitFor(() => {
      expect(setSnackbar).toHaveBeenCalledWith({ text: "Policy denied", severity: "error" })
    })
    expect(result.current.dndEnabled).toBe(false)
  })

  it("disables DND with null server times and reports the disabled state", async () => {
    const setSnackbar = vi.fn()
    mocks.user = {
      ...mocks.user,
      preferences: { dnd_enabled: true, dnd_start: "22:00:00", dnd_end: "07:00:00" },
    }
    const updatedUser = {
      ...mocks.user,
      preferences: { dnd_enabled: false, dnd_start: null, dnd_end: null },
    }
    mocks.put.mockResolvedValue({ data: updatedUser })
    const { result } = renderHook(() => useDndSettings(setSnackbar))

    act(() => {
      result.current.handleDndToggle({} as ChangeEvent<HTMLInputElement>, false)
    })

    await vi.waitFor(() => expect(mocks.put).toHaveBeenCalled())
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
      ...mocks.user,
      preferences: { dnd_enabled: true, dnd_start: "22:00:00", dnd_end: "07:00:00" },
    }
    const updatedUser = {
      ...mocks.user,
      preferences: { dnd_enabled: true, dnd_start: "23:45:30", dnd_end: "08:00:00" },
    }
    mocks.put.mockResolvedValue({ data: updatedUser })
    const { result } = renderHook(() => useDndSettings(setSnackbar))

    act(() => {
      result.current.handleDndStartChange(changeEvent("23:45:30"))
      result.current.handleDndStartBlur(blurEvent("23:45:30"))
    })

    await vi.waitFor(() => expect(mocks.put).toHaveBeenCalled())
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
      ...mocks.user,
      preferences: { dnd_enabled: true, dnd_start: "22:00:00", dnd_end: "07:00:00" },
    }
    mocks.put.mockResolvedValue({
      data: {
        ...mocks.user,
        preferences: { dnd_enabled: true, dnd_start: "22:00:00", dnd_end: "invalid" },
      },
    })
    const { result } = renderHook(() => useDndSettings(setSnackbar))

    act(() => {
      result.current.handleDndEndChange(changeEvent("invalid"))
      result.current.handleDndEndBlur(blurEvent("invalid"))
    })

    await vi.waitFor(() => expect(mocks.put).toHaveBeenCalled())
    expect(mocks.put).toHaveBeenCalledWith("/users/me", {
      preferences: { dnd_enabled: true, dnd_start: "22:00:00", dnd_end: "invalid" },
    })
  })

  it("validates an empty end-time blur without issuing a write", async () => {
    const setSnackbar = vi.fn()
    mocks.user = {
      ...mocks.user,
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
      ...mocks.user,
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
    act(() => {
      result.current.handleDndToggle({} as ChangeEvent<HTMLInputElement>, true)
    })
    await vi.waitFor(() => expect(mocks.put).toHaveBeenCalledTimes(1))

    act(() => {
      result.current.handleDndToggle({} as ChangeEvent<HTMLInputElement>, false)
    })
    expect(mocks.put).toHaveBeenCalledTimes(1)
    resolvePut({ data: mocks.user })
    await vi.waitFor(() => expect(result.current.dndSaving).toBe(false))
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

    act(() => {
      result.current.handleDndToggle({} as ChangeEvent<HTMLInputElement>, true)
    })

    await vi.waitFor(() =>
      expect(setSnackbar).toHaveBeenCalledWith({
        text: "Start is invalid; End is invalid",
        severity: "error",
      })
    )
    await vi.waitFor(() => expect(result.current.dndSaving).toBe(false))
  })

  it("uses the generic fallback for a non-Axios persistence failure", async () => {
    const setSnackbar = vi.fn()
    mocks.put.mockRejectedValue({ reason: "offline" })
    const { result } = renderHook(() => useDndSettings(setSnackbar))

    act(() => {
      result.current.handleDndToggle({} as ChangeEvent<HTMLInputElement>, true)
    })

    await vi.waitFor(() =>
      expect(setSnackbar).toHaveBeenCalledWith({
        text: "settings:dnd.snackbar.updateFailed",
        severity: "error",
      })
    )
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

    act(() => {
      result.current.handleDndToggle({} as ChangeEvent<HTMLInputElement>, true)
    })

    await vi.waitFor(() =>
      expect(setSnackbar).toHaveBeenCalledWith({
        text: "settings:dnd.snackbar.updateFailed",
        severity: "error",
      })
    )
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

    act(() => {
      result.current.handleDndToggle({} as ChangeEvent<HTMLInputElement>, true)
    })

    await vi.waitFor(() =>
      expect(setSnackbar).toHaveBeenCalledWith({
        text: "settings:dnd.snackbar.updateFailed",
        severity: "error",
      })
    )
  })
})
