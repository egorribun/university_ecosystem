import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { LazyMotion, domAnimation } from "framer-motion"
import { beforeEach, describe, expect, it, vi } from "vitest"

const profileState = vi.hoisted(() => ({
  avatarInputRef: { current: null as HTMLInputElement | null },
  coverInputRef: { current: null as HTMLInputElement | null },
  identityLoading: false,
  userId: "8b1f0c3e-5d2a-4e7b-9c41-2f6a8d0e1b35",
  avatarBusy: false,
  coverBusy: false,
  triggerAvatarPick: vi.fn(),
  triggerCoverPick: vi.fn(),
  removeAvatar: vi.fn(),
  removeCover: vi.fn(),
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => vi.fn(),
}))

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { id: profileState.userId, full_name: "Test User" },
    loading: profileState.identityLoading,
  }),
}))

vi.mock("@/pages/settings/hooks/useAvatarUpload", () => ({
  useAvatarUpload: () => ({
    avatarSrc: "https://example.test/avatar.png",
    handleError: vi.fn(),
    triggerPick: profileState.triggerAvatarPick,
    busy: profileState.avatarBusy,
    remove: profileState.removeAvatar,
    inputRef: profileState.avatarInputRef,
    upload: vi.fn(),
  }),
}))

vi.mock("@/pages/settings/hooks/useCoverUpload", () => ({
  useCoverUpload: () => ({
    coverSrc: "",
    coverUrl: "/media/cover.png",
    triggerPick: profileState.triggerCoverPick,
    busy: profileState.coverBusy,
    remove: profileState.removeCover,
    inputRef: profileState.coverInputRef,
    upload: vi.fn(),
  }),
}))

import { ProfileSection } from "../ProfileSection"

beforeEach(() => {
  vi.clearAllMocks()
  profileState.identityLoading = false
  profileState.userId = "8b1f0c3e-5d2a-4e7b-9c41-2f6a8d0e1b35"
  profileState.avatarBusy = false
  profileState.coverBusy = false
  profileState.avatarInputRef.current = null
  profileState.coverInputRef.current = null
})

describe("ProfileSection identity readiness", () => {
  it.each(["avatar", "cover"] as const)(
    "blocks %s actions until identity is ready, including repeated loading",
    async (media) => {
      const user = userEvent.setup()
      profileState.identityLoading = true
      const view = () => (
        <LazyMotion features={domAnimation}>
          <ProfileSection setSnackbar={vi.fn()} />
        </LazyMotion>
      )
      const { rerender } = render(view())
      await user.click(
        screen.getByRole("button", {
          name:
            media === "avatar" ? /settings:media\.avatar\.title/ : /settings:media\.cover\.title/,
        })
      )
      const change = screen.getByRole("button", { name: `settings:media.${media}.change` })
      const remove = screen.getByRole("button", {
        name: `settings:media.${media}.${media === "avatar" ? "delete" : "remove"}`,
      })
      const pick =
        media === "avatar" ? profileState.triggerAvatarPick : profileState.triggerCoverPick
      const removeMedia = media === "avatar" ? profileState.removeAvatar : profileState.removeCover

      expect(change).toBeDisabled()
      expect(remove).toBeDisabled()
      await user.click(change)
      await user.click(remove)
      expect(pick).not.toHaveBeenCalled()
      expect(removeMedia).not.toHaveBeenCalled()

      profileState.identityLoading = false
      rerender(view())
      expect(change).toBeEnabled()
      expect(remove).toBeEnabled()
      await user.click(change)
      await user.click(remove)
      expect(pick).toHaveBeenCalledTimes(1)
      expect(removeMedia).toHaveBeenCalledTimes(1)

      profileState.identityLoading = true
      rerender(view())
      expect(change).toBeDisabled()
      expect(remove).toBeDisabled()

      profileState.identityLoading = false
      profileState.avatarBusy = media === "avatar"
      profileState.coverBusy = media === "cover"
      rerender(view())
      expect(change).toBeDisabled()
      expect(remove).toBeDisabled()
    }
  )

  it.each([
    ["the server-render role stub", "ssr-stub"],
    ["the encrypted-cache placeholder", "-1"],
  ])("keeps media actions disabled for %s until the confirmed account arrives", async (_, id) => {
    const user = userEvent.setup()
    profileState.userId = id
    const view = () => (
      <LazyMotion features={domAnimation}>
        <ProfileSection setSnackbar={vi.fn()} />
      </LazyMotion>
    )
    const { rerender } = render(view())
    await user.click(screen.getByRole("button", { name: /settings:media\.avatar\.title/ }))
    const change = screen.getByRole("button", { name: "settings:media.avatar.change" })
    const remove = screen.getByRole("button", { name: "settings:media.avatar.delete" })

    // Loading has finished, but the click would be dropped by the session guard.
    expect(change).toBeDisabled()
    expect(remove).toBeDisabled()
    await user.click(remove)
    expect(profileState.removeAvatar).not.toHaveBeenCalled()

    profileState.userId = "8b1f0c3e-5d2a-4e7b-9c41-2f6a8d0e1b35"
    rerender(view())
    expect(change).toBeEnabled()
    expect(remove).toBeEnabled()
    await user.click(remove)
    expect(profileState.removeAvatar).toHaveBeenCalledTimes(1)
  })
})
