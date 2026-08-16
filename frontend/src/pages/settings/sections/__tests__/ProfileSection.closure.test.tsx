import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { LazyMotion, domAnimation } from "framer-motion"
import { beforeEach, describe, expect, it, vi } from "vitest"

const profileState = vi.hoisted(() => ({
  navigate: vi.fn(),
  avatarInputRef: { current: null as HTMLInputElement | null },
  coverInputRef: { current: null as HTMLInputElement | null },
  uploadAvatar: vi.fn(),
  uploadCover: vi.fn(),
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
  useAuth: () => ({ user: { full_name: profileState.fullName } }),
}))

vi.mock("@/pages/settings/hooks/useAvatarUpload", () => ({
  useAvatarUpload: () => ({
    avatarSrc: "https://example.test/avatar.png",
    handleError: vi.fn(),
    triggerPick: vi.fn(),
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
    triggerPick: vi.fn(),
    busy: false,
    remove: vi.fn(),
    inputRef: profileState.coverInputRef,
    upload: profileState.uploadCover,
  }),
}))

import { ProfileSection } from "../ProfileSection"

beforeEach(() => {
  profileState.navigate.mockClear()
  profileState.uploadAvatar.mockClear()
  profileState.uploadCover.mockClear()
  profileState.avatarInputRef.current = null
  profileState.coverInputRef.current = null
  profileState.fullName = ""
  profileState.coverSrc = ""
  profileState.coverUrl = null
})

describe("ProfileSection closure", () => {
  it("renders empty-profile fallbacks and navigates to profile editing", async () => {
    const user = userEvent.setup()
    render(
      <LazyMotion features={domAnimation}>
        <ProfileSection setSnackbar={vi.fn()} />
      </LazyMotion>
    )

    expect(screen.getByAltText("avatar")).toBeInTheDocument()
    expect(screen.getByTestId("settings-cover-preview")).toHaveStyle({
      background: "var(--bg-surface-hover)",
    })

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
    fireEvent.change(avatarInput!, { target: { files: [avatarFile] } })
    fireEvent.change(coverInput!, { target: { files: [coverFile] } })

    expect(profileState.uploadAvatar).toHaveBeenCalledWith(avatarFile)
    expect(profileState.uploadCover).toHaveBeenCalledWith(coverFile)
  })
})
