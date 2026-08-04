import { act, renderHook } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  api: {
    post: vi.fn(),
    delete: vi.fn(),
  },
  fetchCurrentUser: vi.fn(),
  fetchQuery: vi.fn(),
  setUser: vi.fn(),
  useAuth: vi.fn(),
  t: vi.fn((key: string) => key),
}))

vi.mock("@/api/client", () => ({ default: mocks.api }))
vi.mock("@/contexts/AuthContext", () => ({ useAuth: mocks.useAuth }))
vi.mock("@/hooks/auth/useProfileSync", () => ({
  currentUserQueryKey: ["users", "me"],
  fetchCurrentUser: mocks.fetchCurrentUser,
}))
vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ fetchQuery: mocks.fetchQuery }),
}))
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: mocks.t }),
}))

import { useAvatarUpload } from "@/pages/settings/hooks/useAvatarUpload"
import { useCoverUpload } from "@/pages/settings/hooks/useCoverUpload"

const user = {
  id: "user-1",
  avatar_url: "/media/avatar.png",
  cover_url: "/media/cover.png",
}

const freshUser = {
  ...user,
  avatar_url: "/media/avatar-new.png",
  cover_url: "/media/cover-new.png",
}

const imageFile = (name = "photo.png") => new File(["image"], name, { type: "image/png" })

const oversizedImage = () => {
  const file = imageFile("large.png")
  Object.defineProperty(file, "size", { configurable: true, value: 13 * 1024 * 1024 })
  return file
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.useAuth.mockReturnValue({ user, setUser: mocks.setUser })
  mocks.fetchQuery.mockImplementation(
    async (options: { queryFn: (context: { signal: AbortSignal }) => Promise<unknown> }) => {
      await options.queryFn({ signal: undefined as unknown as AbortSignal })
      return freshUser
    }
  )
  mocks.fetchCurrentUser.mockResolvedValue(freshUser)
  mocks.api.post.mockResolvedValue({ data: {} })
  mocks.api.delete.mockResolvedValue({ data: {} })
})

describe.each([
  ["avatar", useAvatarUpload, "/users/me/avatar", "settings:media.avatar"],
  ["cover", useCoverUpload, "/users/me/cover", "settings:media.cover"],
] as const)("use%sUpload", (kind, useUpload, endpoint, copyPrefix) => {
  it("builds the current image URL and opens the file picker", () => {
    const { result } = renderHook(() => useUpload(vi.fn()))
    const click = vi.fn()

    act(() => result.current.triggerPick())
    result.current.inputRef.current = { click } as unknown as HTMLInputElement

    act(() => result.current.triggerPick())

    const src = kind === "avatar" ? result.current.avatarSrc : result.current.coverSrc
    expect(src).toContain("_v=")
    expect(click).toHaveBeenCalledOnce()
  })

  it("uses the empty-image fallback when the profile has no image URL", () => {
    mocks.useAuth.mockReturnValue({
      user: { ...user, avatar_url: null, cover_url: null },
      setUser: mocks.setUser,
    })
    const { result } = renderHook(() => useUpload(vi.fn()))

    const src = kind === "avatar" ? result.current.avatarSrc : result.current.coverSrc
    if (kind === "avatar") {
      expect(src).toEqual(expect.stringContaining("gravatar.com/avatar"))
    } else {
      expect(src).toBe("")
    }
  })

  it("rejects unsupported formats and oversized files before the request", async () => {
    const setSnackbar = vi.fn()
    const { result } = renderHook(() => useUpload(setSnackbar))

    await act(async () => {
      await result.current.upload(new File(["text"], "notes.txt", { type: "text/plain" }))
    })
    expect(setSnackbar).toHaveBeenLastCalledWith({
      text: "settings:media.validation.supportedFormats",
      severity: "error",
    })
    expect(mocks.api.post).not.toHaveBeenCalled()

    await act(async () => {
      await result.current.upload(oversizedImage())
    })
    expect(setSnackbar).toHaveBeenLastCalledWith({
      text: "settings:media.validation.fileTooLarge",
      severity: "error",
    })
    expect(mocks.api.post).not.toHaveBeenCalled()
  })

  it("uploads a valid image, refreshes the profile, and reports success", async () => {
    const setSnackbar = vi.fn()
    const { result } = renderHook(() => useUpload(setSnackbar))

    await act(async () => {
      await result.current.upload(imageFile())
    })

    expect(mocks.api.post).toHaveBeenCalledWith(
      endpoint,
      expect.any(FormData),
      expect.objectContaining({ headers: { "Content-Type": "multipart/form-data" } })
    )
    expect(mocks.fetchQuery).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["users", "me"], staleTime: 0 })
    )
    expect(mocks.setUser).toHaveBeenCalledWith(freshUser)
    expect(setSnackbar).toHaveBeenLastCalledWith({
      text: `${copyPrefix}.updated`,
      severity: "success",
    })
    expect(result.current.busy).toBe(false)
  })

  it("reports upload failures and always clears busy state", async () => {
    const setSnackbar = vi.fn()
    mocks.api.post.mockRejectedValueOnce(new Error("upload failed"))
    const { result } = renderHook(() => useUpload(setSnackbar))

    await act(async () => {
      await result.current.upload(imageFile())
    })

    expect(setSnackbar).toHaveBeenLastCalledWith({
      text: `${copyPrefix}.uploadFailed`,
      severity: "error",
    })
    expect(result.current.busy).toBe(false)
  })

  it("removes the image and handles delete failures", async () => {
    const setSnackbar = vi.fn()
    const { result } = renderHook(() => useUpload(setSnackbar))

    await act(async () => {
      await result.current.remove()
    })
    expect(mocks.api.delete).toHaveBeenCalledWith(endpoint)
    expect(setSnackbar).toHaveBeenLastCalledWith({
      text: `${copyPrefix}.deleted`,
      severity: "success",
    })

    mocks.api.delete.mockRejectedValueOnce(new Error("delete failed"))
    await act(async () => {
      await result.current.remove()
    })
    expect(setSnackbar).toHaveBeenLastCalledWith({
      text: `${copyPrefix}.deleteFailed`,
      severity: "error",
    })
    expect(result.current.busy).toBe(false)
  })

  if (kind === "avatar") {
    it("falls back to the default avatar when the image reports an error", () => {
      const { result } = renderHook(() => useUpload(vi.fn()))
      const image = document.createElement("img")

      act(() => {
        result.current.handleError({ currentTarget: image } as never)
      })

      expect(image.src).toContain("gravatar.com/avatar/00000000000000000000000000000000")
    })
  }
})
