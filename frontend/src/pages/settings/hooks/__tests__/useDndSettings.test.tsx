import type { ChangeEvent, FocusEvent } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { act, renderHook } from "@testing-library/react"
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
})
