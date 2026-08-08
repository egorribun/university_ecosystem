import type { ReactNode } from "react"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { User } from "@/types/User"

const { authState, apiState, mediaState, nowPlayingState, navigate } = vi.hoisted(() => ({
  authState: {
    user: null as User | null,
    loading: false,
    setUser: vi.fn(),
  },
  apiState: {
    put: vi.fn(),
  },
  mediaState: {} as Record<string, boolean>,
  nowPlayingState: {
    data: null as unknown,
  },
  navigate: vi.fn(),
}))

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => authState,
}))

vi.mock("@/api/client", () => ({
  default: apiState,
}))

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => navigate,
}))

vi.mock("@/hooks/useMediaQuery", () => ({
  default: (query: string) => mediaState[query] ?? false,
}))

vi.mock("@/hooks/useNowPlaying", () => ({
  useNowPlaying: () => ({ data: nowPlayingState.data }),
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: unknown) => (typeof fallback === "string" ? fallback : key),
  }),
}))

vi.mock("framer-motion", () => ({
  m: {
    div: ({ children, className }: { children?: ReactNode; className?: string }) => (
      <div className={className}>{children}</div>
    ),
  },
}))

vi.mock("@/components/Layout", () => ({
  default: ({ children }: { children?: ReactNode }) => <main>{children}</main>,
}))

vi.mock("@/components/motion/PageFadeIn", () => ({
  default: ({ children }: { children?: ReactNode }) => <>{children}</>,
}))

vi.mock("@/components/ui/SEO", () => ({
  SEO: () => null,
}))

vi.mock("qrcode.react", () => ({
  QRCodeSVG: ({ value }: { value: string }) => <svg data-testid="qr-code" data-value={value} />,
}))

vi.mock("@/components/settings", () => {
  function Button({
    as,
    children,
    disabled,
    href,
    onClick,
  }: {
    as?: "a" | "button"
    children?: ReactNode
    disabled?: boolean
    href?: string
    onClick?: () => void
  }) {
    if (as === "a") return <a href={href}>{children}</a>
    return (
      <button type="button" disabled={disabled} onClick={onClick}>
        {children}
      </button>
    )
  }

  function Dialog({
    children,
    onClose,
    open,
  }: {
    children?: ReactNode
    onClose?: () => void
    open: boolean
  }) {
    if (!open) return null
    return (
      <div role="dialog">
        {children}
        <button type="button" aria-label="close dialog" onClick={onClose} />
      </div>
    )
  }

  const DialogTitle = ({ children }: { children?: ReactNode }) => <h2>{children}</h2>
  const DialogContent = ({ children }: { children?: ReactNode }) => <div>{children}</div>
  const DialogActions = ({ children }: { children?: ReactNode }) => <div>{children}</div>
  const Alert = ({ children, onClose }: { children?: ReactNode; onClose?: () => void }) => (
    <div>
      <button type="button" aria-label="close alert" onClick={onClose} />
      {children}
    </div>
  )
  const Snackbar = ({
    children,
    onClose,
    open,
  }: {
    children?: ReactNode
    onClose?: () => void
    open: boolean
  }) =>
    open ? (
      <div data-testid="snackbar">
        <button type="button" aria-label="close snackbar" onClick={onClose} />
        {children}
      </div>
    ) : null

  return { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, Snackbar }
})

vi.mock("@/components/profile", () => {
  const ProfileSkeleton = () => <div data-testid="profile-skeleton" />
  const ProfileBackdrop = () => <div data-testid="profile-backdrop" />
  const NowPlayingCard = () => <div data-testid="now-playing-card" />

  const ProfileHeader = ({
    onEmailClick,
    onQrClick,
    onTelegramClick,
  }: {
    onEmailClick: () => void
    onQrClick: () => void
    onTelegramClick: () => void
  }) => (
    <div data-testid="profile-header">
      <button type="button" data-testid="email-button" onClick={onEmailClick} />
      <button type="button" data-testid="telegram-button" onClick={onTelegramClick} />
      <button type="button" data-testid="qr-button" onClick={onQrClick} />
    </div>
  )

  const ProfileDetails = ({ isOpen, onToggle }: { isOpen: boolean; onToggle: () => void }) => (
    <section>
      <button type="button" onClick={onToggle}>
        toggle details
      </button>
      <span data-testid="details-state">{String(isOpen)}</span>
    </section>
  )

  const AchievementsSection = ({
    achievements,
    onAchievementClick,
  }: {
    achievements: Array<{ name: string }>
    onAchievementClick: (achievement: { name: string; issuer?: string; url?: string }) => void
  }) => (
    <section>
      {achievements.map((achievement) => (
        <button
          type="button"
          key={achievement.name}
          onClick={() => onAchievementClick(achievement)}
        >
          {achievement.name}
        </button>
      ))}
    </section>
  )

  const ProfileEditor = ({
    fullName,
    onCancel,
    onSave,
    saving,
    setFullName,
  }: {
    fullName: string
    onCancel: () => void
    onSave: () => void
    saving: boolean
    setFullName: (value: string) => void
  }) => (
    <section data-testid="profile-editor">
      <input
        aria-label="full name"
        value={fullName}
        onChange={(event) => setFullName(event.target.value)}
      />
      <span data-testid="saving-state">{String(saving)}</span>
      <button type="button" onClick={onSave} disabled={saving}>
        save profile
      </button>
      <button type="button" onClick={onCancel}>
        cancel profile
      </button>
    </section>
  )

  return {
    AchievementsSection,
    NowPlayingCard,
    ProfileBackdrop,
    ProfileDetails,
    ProfileEditor,
    ProfileHeader,
    ProfileSkeleton,
    buildVCardString: () => "BEGIN:VCARD",
    calculateAvatarSize: (isMobile: boolean, isWideScreen: boolean) =>
      isMobile ? 80 : isWideScreen ? 160 : 120,
    calculateHeroLayout: (avatarSize: number) => ({ heroPaddingBottom: avatarSize }),
    calculateStatusIndicator: () => ({ offset: 2, size: 16 }),
    parseAchievements: (value: unknown) =>
      value ? [{ name: "Award", issuer: "University", url: "https://example.test/award" }] : [],
  }
})

import Profile from "@/pages/Profile"

const user = {
  id: "user-1",
  full_name: "Ada Lovelace",
  email: "ada@example.com",
  role: "student",
  is_online: true,
  spotify_connected: true,
  profile_detail: {
    about: "Builds analytical engines",
    status: "active",
    telegram: "@ada",
    achievements: "Award",
    department: "Computing",
    position: "Student",
  },
  education_path: {
    record_book_number: "RB-1",
    institute: "Institute",
    course: "2",
    education_level: "bachelor",
    track: "Software",
    program: "Computer Science",
  },
} as unknown as User

describe("Profile behavior", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authState.user = user
    authState.loading = false
    authState.setUser.mockReset()
    apiState.put.mockResolvedValue({ data: user })
    nowPlayingState.data = {
      track_id: "track-1",
      track_name: "Analytical Engine",
      artists: ["Ada"],
    }
    Object.keys(mediaState).forEach((key) => delete mediaState[key])
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllEnvs()
  })

  it("renders the loading skeleton before user data is ready", () => {
    authState.loading = true

    render(<Profile />)

    expect(screen.getByTestId("profile-skeleton")).toBeInTheDocument()
    expect(screen.queryByTestId("profile-root")).not.toBeInTheDocument()
  })

  it("renders profile details, now playing, responsive backdrop, and dialogs", () => {
    mediaState["(max-width: 768px)"] = true
    mediaState["(min-width: 1440px)"] = true
    mediaState["(max-width: 1200px)"] = true
    render(<Profile />)

    expect(screen.getByTestId("profile-root")).toBeInTheDocument()
    expect(screen.getByTestId("now-playing-card")).toBeInTheDocument()
    expect(screen.getByTestId("profile-backdrop")).toBeInTheDocument()
    expect(screen.getByTestId("details-state")).toHaveTextContent("true")

    fireEvent.click(screen.getByText("toggle details"))
    expect(screen.getByTestId("details-state")).toHaveTextContent("false")

    fireEvent.click(screen.getByTestId("qr-button"))
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(screen.getByTestId("qr-code")).toHaveAttribute("data-value", "BEGIN:VCARD")
    fireEvent.click(screen.getByRole("button", { name: "close dialog" }))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()

    fireEvent.click(screen.getByTestId("qr-button"))
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.done" }))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Award" }))
    expect(screen.getByRole("dialog")).toHaveTextContent("Award")
    expect(
      screen.getByRole("link", { name: "profile:dialog.achievement.openLink" })
    ).toHaveAttribute("href", "https://example.test/award")
    fireEvent.click(screen.getByRole("button", { name: "close dialog" }))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Award" }))
    fireEvent.click(screen.getByRole("button", { name: "profile:dialog.achievement.close" }))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("shows copy feedback from the contact actions", () => {
    render(<Profile />)

    fireEvent.click(screen.getByTestId("email-button"))
    expect(screen.getByTestId("snackbar")).toHaveTextContent("profile:snackbar.copied")
    fireEvent.click(screen.getByRole("button", { name: "close snackbar" }))
    expect(screen.queryByTestId("snackbar")).not.toBeInTheDocument()

    fireEvent.click(screen.getByTestId("telegram-button"))
    expect(screen.getByTestId("snackbar")).toHaveTextContent("profile:snackbar.copied")
    fireEvent.click(screen.getByRole("button", { name: "close alert" }))
    expect(screen.queryByTestId("snackbar")).not.toBeInTheDocument()
  })

  it("enters edit mode and saves the complete profile payload", async () => {
    const updatedUser = { ...user, full_name: "Grace Lovelace" } as User
    apiState.put.mockResolvedValueOnce({ data: updatedUser })
    render(<Profile />)

    fireEvent.click(screen.getByText("profile:buttons.edit"))
    expect(screen.getByTestId("profile-editor")).toBeInTheDocument()
    fireEvent.change(screen.getByRole("textbox", { name: "full name" }), {
      target: { value: "Grace Lovelace" },
    })
    fireEvent.click(screen.getByRole("button", { name: "save profile" }))

    await waitFor(() => expect(apiState.put).toHaveBeenCalledOnce())
    expect(apiState.put).toHaveBeenCalledWith(
      "/users/me",
      expect.objectContaining({
        full_name: "Grace Lovelace",
        email: user.email,
        profile_detail: expect.objectContaining({ telegram: "@ada" }),
        education_path: expect.objectContaining({ program: "Computer Science" }),
      })
    )
    expect(authState.setUser).toHaveBeenCalledWith(updatedUser)
    expect(navigate).toHaveBeenCalledWith({ to: "/profile", replace: true })
    expect(screen.getByTestId("snackbar")).toHaveTextContent("profile:snackbar.profileUpdated")
  })

  it("renders a server string validation error while leaving edit mode active", async () => {
    apiState.put.mockRejectedValueOnce({ response: { data: { detail: "Email is already used" } } })
    render(<Profile />)

    fireEvent.click(screen.getByText("profile:buttons.edit"))
    fireEvent.click(screen.getByRole("button", { name: "save profile" }))

    await waitFor(() =>
      expect(screen.getByTestId("snackbar")).toHaveTextContent("Email is already used")
    )
    expect(screen.getByTestId("profile-editor")).toBeInTheDocument()
    expect(authState.setUser).not.toHaveBeenCalled()
  })

  it("joins structured validation errors and handles generic failures", async () => {
    apiState.put.mockRejectedValueOnce({
      response: {
        data: { detail: [{ msg: "Name is required" }, { message: "Email is invalid" }] },
      },
    })
    render(<Profile />)

    fireEvent.click(screen.getByText("profile:buttons.edit"))
    fireEvent.click(screen.getByRole("button", { name: "save profile" }))
    await waitFor(() =>
      expect(screen.getByTestId("snackbar")).toHaveTextContent("Name is required; Email is invalid")
    )

    apiState.put.mockRejectedValueOnce(new Error("network down"))
    fireEvent.click(screen.getByRole("button", { name: "save profile" }))
    await waitFor(() =>
      expect(screen.getByTestId("snackbar")).toHaveTextContent("profile:snackbar.error")
    )
  })

  it("cancels edit mode and navigates back to the profile route", () => {
    render(<Profile />)

    fireEvent.click(screen.getByText("profile:buttons.edit"))
    fireEvent.click(screen.getByRole("button", { name: "cancel profile" }))

    expect(screen.queryByTestId("profile-editor")).not.toBeInTheDocument()
    expect(navigate).toHaveBeenCalledWith({ to: "/profile", replace: true })
  })

  it("omits now playing when Spotify is disconnected or data is empty", () => {
    authState.user = { ...user, spotify_connected: false } as User
    nowPlayingState.data = null

    render(<Profile />)

    expect(screen.queryByTestId("now-playing-card")).not.toBeInTheDocument()
  })

  it("accepts each supported now-playing identity field", () => {
    nowPlayingState.data = { track_id: "", track_name: "Named track", artists: [] }
    const { rerender } = render(<Profile />)
    expect(screen.getByTestId("now-playing-card")).toBeInTheDocument()

    nowPlayingState.data = { track_id: "", track_name: "", artists: ["Artist"] }
    rerender(<Profile />)
    expect(screen.getByTestId("now-playing-card")).toBeInTheDocument()

    nowPlayingState.data = { track_id: "", track_name: "", artists: [] }
    rerender(<Profile />)
    expect(screen.queryByTestId("now-playing-card")).not.toBeInTheDocument()
  })

  it("uses online and field defaults for partially populated users", () => {
    authState.user = {
      ...user,
      full_name: "",
      email: "",
      is_online: undefined,
      online: false,
      profile_detail: {},
      education_path: {},
      spotify_connected: false,
    } as User

    render(<Profile />)

    expect(screen.getByTestId("profile-root")).toBeInTheDocument()
    expect(screen.queryByTestId("now-playing-card")).not.toBeInTheDocument()
  })

  it("uses the null-user view without attempting Spotify playback", () => {
    authState.user = null

    render(<Profile />)

    expect(screen.getByTestId("profile-root")).toBeInTheDocument()
    expect(screen.queryByTestId("now-playing-card")).not.toBeInTheDocument()
  })

  it("renders production motion transitions when the app is not in test mode", async () => {
    vi.stubEnv("MODE", "production")
    vi.resetModules()
    const { default: ProductionProfile } = await import("@/pages/Profile")

    render(<ProductionProfile />)

    expect(screen.getByTestId("profile-root")).toBeInTheDocument()
    expect(screen.getByTestId("profile-header")).toBeInTheDocument()
  })
})
