import { expectInlineBackground } from "@/tests/helpers/expectInlineBackground"
import { act, fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { LazyMotion, domAnimation } from "framer-motion"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { invalidateSessionEpoch, rotateBrowserSession } from "@/stores/sessionEpoch"

const profileState = vi.hoisted(() => ({
  navigate: vi.fn(),
  avatarInputRef: { current: null as HTMLInputElement | null },
  coverInputRef: { current: null as HTMLInputElement | null },
  uploadAvatar: vi.fn(),
  uploadCover: vi.fn(),
  triggerAvatarPick: vi.fn(),
  triggerCoverPick: vi.fn(),
  userId: "user-1",
  loading: false,
  fullName: "",
  coverSrc: "",
  coverUrl: null as string | null,
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => profileState.navigate,
}))

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { id: profileState.userId, full_name: profileState.fullName },
    loading: profileState.loading,
  }),
}))

vi.mock("@/pages/settings/hooks/useAvatarUpload", () => ({
  useAvatarUpload: () => ({
    avatarSrc: "https://example.test/avatar.png",
    handleError: vi.fn(),
    triggerPick: profileState.triggerAvatarPick,
    busy: false,
    remove: vi.fn(),
    inputRef: profileState.avatarInputRef,
    upload: profileState.uploadAvatar,
  }),
}))

vi.mock("@/pages/settings/hooks/useCoverUpload", () => ({
  useCoverUpload: () => ({
    coverSrc: profileState.coverSrc,
    coverUrl: profileState.coverUrl,
    triggerPick: profileState.triggerCoverPick,
    busy: false,
    remove: vi.fn(),
    inputRef: profileState.coverInputRef,
    upload: profileState.uploadCover,
  }),
}))

import { ProfileSection } from "../ProfileSection"

beforeEach(() => {
  rotateBrowserSession()
  profileState.navigate.mockClear()
  profileState.uploadAvatar.mockClear()
  profileState.uploadCover.mockClear()
  profileState.triggerAvatarPick.mockClear()
  profileState.triggerCoverPick.mockClear()
  profileState.avatarInputRef.current = null
  profileState.coverInputRef.current = null
  profileState.fullName = ""
  profileState.coverSrc = ""
  profileState.coverUrl = null
  profileState.userId = "user-1"
  profileState.loading = false
})

const view = () => (
  <LazyMotion features={domAnimation}>
    <ProfileSection setSnackbar={vi.fn()} />
  </LazyMotion>
)

const openPicker = (media: "avatar" | "cover") => {
  const title = screen.getByRole("button", {
    name: media === "avatar" ? /settings:media\.avatar\.title/ : /settings:media\.cover\.title/,
  })
  if (title.getAttribute("aria-expanded") !== "true") fireEvent.click(title)
  fireEvent.click(screen.getByRole("button", { name: `settings:media.${media}.change` }))
}

describe("ProfileSection closure", () => {
  it("renders empty-profile fallbacks and navigates to profile editing", async () => {
    const user = userEvent.setup()
    render(
      <LazyMotion features={domAnimation}>
        <ProfileSection setSnackbar={vi.fn()} />
      </LazyMotion>
    )

    expect(screen.getByAltText("avatar")).toBeInTheDocument()
    expectInlineBackground(screen.getByTestId("settings-cover-preview"), "var(--bg-surface-hover)")

    await user.click(
      screen.getByRole("button", { name: /settings:account\.profile\.extra\.title/ })
    )
    await user.click(screen.getByRole("button", { name: "common:buttons.edit" }))

    expect(profileState.navigate).toHaveBeenCalledWith({
      to: "/profile",
      search: { edit: "1" },
    })
  })

  it("renders configured media and forwards selected files to each uploader", () => {
    profileState.fullName = "Ada Lovelace"
    profileState.coverSrc = "https://example.test/cover.png"
    profileState.coverUrl = "/media/cover.png"
    const { container } = render(
      <LazyMotion features={domAnimation}>
        <ProfileSection setSnackbar={vi.fn()} />
      </LazyMotion>
    )

    expect(screen.getByAltText("Ada Lovelace")).toBeInTheDocument()
    expect(screen.getByTestId("settings-cover-preview").style.background).toContain(
      "https://example.test/cover.png"
    )
    expect(screen.getByText("settings:media.cover.remove")).toBeInTheDocument()

    const [avatarInput, coverInput] =
      container.querySelectorAll<HTMLInputElement>('input[type="file"]')
    const avatarFile = new File(["avatar"], "avatar.png", { type: "image/png" })
    const coverFile = new File(["cover"], "cover.png", { type: "image/png" })
    openPicker("avatar")
    openPicker("cover")
    fireEvent.change(avatarInput!, { target: { files: [avatarFile] } })
    fireEvent.change(coverInput!, { target: { files: [coverFile] } })

    expect(profileState.uploadAvatar).toHaveBeenCalledWith(avatarFile)
    expect(profileState.uploadCover).toHaveBeenCalledWith(coverFile)
  })

  it("ignores empty file selections", () => {
    const { container } = render(
      <LazyMotion features={domAnimation}>
        <ProfileSection setSnackbar={vi.fn()} />
      </LazyMotion>
    )

    const [avatarInput, coverInput] =
      container.querySelectorAll<HTMLInputElement>('input[type="file"]')
    fireEvent.change(avatarInput!, { target: { files: [] } })
    fireEvent.change(coverInput!, { target: { files: [] } })

    expect(profileState.uploadAvatar).not.toHaveBeenCalled()
    expect(profileState.uploadCover).not.toHaveBeenCalled()
  })

  it.each(["avatar", "cover"] as const)(
    "consumes the %s pick once and allows a fresh pick in the same session",
    (media) => {
      const { container } = render(view())
      const input =
        container.querySelectorAll<HTMLInputElement>('input[type="file"]')[
          media === "avatar" ? 0 : 1
        ]!
      const upload = media === "avatar" ? profileState.uploadAvatar : profileState.uploadCover
      const file = new File(["image"], "image.png", { type: "image/png" })

      openPicker(media)
      fireEvent.change(input, { target: { files: [file] } })
      expect(upload).toHaveBeenCalledOnce()
      expect(upload).toHaveBeenCalledWith(file)
      fireEvent.change(input, { target: { files: [file] } })
      expect(upload).toHaveBeenCalledOnce()

      openPicker(media)
      fireEvent.change(input, { target: { files: [file] } })
      expect(upload).toHaveBeenCalledTimes(2)
    }
  )

  it.each(
    (["avatar", "cover"] as const).flatMap((media) =>
      (["epoch", "generation", "user"] as const).map((transition) => ({ media, transition }))
    )
  )(
    "rejects an old $media selection after a $transition change and allows a fresh pick",
    ({ media, transition }) => {
      const { container, rerender } = render(view())
      const input =
        container.querySelectorAll<HTMLInputElement>('input[type="file"]')[
          media === "avatar" ? 0 : 1
        ]!
      const upload = media === "avatar" ? profileState.uploadAvatar : profileState.uploadCover
      const file = new File(["image"], "image.png", { type: "image/png" })
      openPicker(media)

      if (transition === "epoch") invalidateSessionEpoch()
      else if (transition === "generation") rotateBrowserSession()
      else profileState.userId = "user-2"
      rerender(view())
      fireEvent.change(input, { target: { files: [file] } })
      expect(upload).not.toHaveBeenCalled()

      openPicker(media)
      fireEvent.change(input, { target: { files: [file] } })
      expect(upload).toHaveBeenCalledOnce()
      expect(upload).toHaveBeenCalledWith(file)
    }
  )

  it.each(["avatar", "cover"] as const)(
    "clears the %s receipt on empty selection or cancellation",
    (media) => {
      const { container } = render(view())
      const input =
        container.querySelectorAll<HTMLInputElement>('input[type="file"]')[
          media === "avatar" ? 0 : 1
        ]!
      const upload = media === "avatar" ? profileState.uploadAvatar : profileState.uploadCover
      const file = new File(["image"], "image.png", { type: "image/png" })

      openPicker(media)
      fireEvent.change(input, { target: { files: [] } })
      fireEvent.change(input, { target: { files: [file] } })
      expect(upload).not.toHaveBeenCalled()

      openPicker(media)
      fireEvent(input, new Event("cancel", { bubbles: true }))
      fireEvent.change(input, { target: { files: [file] } })
      expect(upload).not.toHaveBeenCalled()

      openPicker(media)
      fireEvent.change(input, { target: { files: [file] } })
      expect(upload).toHaveBeenCalledOnce()
    }
  )

  it.each(["avatar", "cover"] as const)(
    "refuses to open %s with an outdated rendered session",
    async (media) => {
      render(view())
      const title = screen.getByRole("button", {
        name: media === "avatar" ? /settings:media\.avatar\.title/ : /settings:media\.cover\.title/,
      })
      fireEvent.click(title)
      await act(async () => {
        invalidateSessionEpoch()
        fireEvent.click(screen.getByRole("button", { name: `settings:media.${media}.change` }))
        expect(
          media === "avatar" ? profileState.triggerAvatarPick : profileState.triggerCoverPick
        ).not.toHaveBeenCalled()
        await Promise.resolve()
      })
    }
  )

  it.each(["avatar", "cover"] as const)(
    "retains a %s receipt through temporary loading in the same session",
    (media) => {
      const { container, rerender } = render(view())
      const input =
        container.querySelectorAll<HTMLInputElement>('input[type="file"]')[
          media === "avatar" ? 0 : 1
        ]!
      const upload = media === "avatar" ? profileState.uploadAvatar : profileState.uploadCover
      const file = new File(["image"], "image.png", { type: "image/png" })
      openPicker(media)
      profileState.loading = true
      rerender(view())
      profileState.loading = false
      rerender(view())
      fireEvent.change(input, { target: { files: [file] } })
      expect(upload).toHaveBeenCalledWith(file)
    }
  )
})
