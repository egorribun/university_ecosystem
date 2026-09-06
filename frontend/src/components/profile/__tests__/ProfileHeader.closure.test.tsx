import { fireEvent, render, screen } from "@testing-library/react"
import { forwardRef, type ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"
import type { User } from "@/types/User"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock("@/components/media/SmartImage", () => ({
  default: ({
    srcRaw,
    fallback,
    alt = "",
    cacheV,
  }: {
    srcRaw?: string
    fallback?: string
    alt?: string
    cacheV?: number
  }) => (
    <img
      data-testid="profile-smart-image"
      src={srcRaw ?? fallback}
      alt={alt}
      data-fallback={fallback}
      data-cache-v={cacheV}
    />
  ),
}))

vi.mock("@/components/ui", () => ({
  Button: forwardRef<
    HTMLButtonElement,
    {
      children?: ReactNode
      onClick?: () => void
      "aria-label"?: string
    }
  >(function MockProfileButton({ children, onClick, ...props }, ref) {
    return (
      <button ref={ref} type="button" onClick={onClick} {...props}>
        {children}
      </button>
    )
  }),
}))

vi.mock("@/components/settings", () => ({
  SectionCard: ({ children }: { children?: ReactNode }) => <section>{children}</section>,
}))

vi.mock("qrcode.react", () => ({
  QRCodeSVG: ({ value }: { value: string }) => <svg data-testid="qr-code" data-value={value} />,
}))

import ProfileHeader from "../ProfileHeader"

const baseProps = {
  avatarVersion: 1,
  coverVersion: 2,
  coverParallax: 8,
  coverScale: 1.04,
  avatarSize: "8rem",
  heroPaddingBottom: "2rem",
  isOnline: true,
  statusOffset: 4,
  statusSize: 10,
  onEmailClick: vi.fn(),
  onTelegramClick: vi.fn(),
  onQrClick: vi.fn(),
  vCardData: "BEGIN:VCARD",
  reduceMotion: false,
  emailButtonRef: { current: null },
  telegramButtonRef: { current: null },
}

describe("ProfileHeader closure paths", () => {
  it("renders complete profile data, online status, and all contact actions", () => {
    const onEmailClick = vi.fn()
    const onTelegramClick = vi.fn()
    const onQrClick = vi.fn()
    const user = {
      id: "u1",
      full_name: "Ada Lovelace",
      email: "ada@example.com",
      avatar_url: "/avatar.jpg",
      cover_url: "/cover.jpg",
      profile_detail: { status: "Researcher", telegram: "@ada" },
      education_path: { course: "Computer Science", record_book_number: "RB-42" },
    } as unknown as User

    const { container } = render(
      <ProfileHeader
        {...baseProps}
        user={user}
        onEmailClick={onEmailClick}
        onTelegramClick={onTelegramClick}
        onQrClick={onQrClick}
      />
    )

    expect(screen.getByRole("heading", { name: "Ada Lovelace" })).toBeInTheDocument()
    expect(screen.getByText("Researcher")).toBeInTheDocument()
    expect(screen.getByText("Computer Science")).toBeInTheDocument()
    expect(screen.getByText("RB-42")).toBeInTheDocument()
    expect(screen.getByText("ada@example.com")).toBeInTheDocument()
    expect(screen.getByText("@ada")).toBeInTheDocument()
    expect(screen.getAllByTestId("profile-smart-image")).toHaveLength(2)
    const images = screen.getAllByTestId("profile-smart-image")
    expect(images[0]).toHaveAttribute("data-cache-v", "2")
    expect(images[0]).toHaveAttribute("src", "/cover.jpg")
    expect(images[1]).toHaveAttribute("data-cache-v", "1")
    expect(images[1]).toHaveAttribute("alt", "Ada Lovelace")
    expect(screen.getByTestId("qr-code")).toHaveAttribute("data-value", "BEGIN:VCARD")

    const hero = [...container.querySelectorAll<HTMLElement>("div")].find((element) =>
      element.className.includes("min-h-(--min-h-hero-cover)")
    )
    expect(hero?.style.paddingBottom).toBe("2rem")
    const cover = images[0]?.parentElement
    expect(cover).toHaveStyle({
      transform: "translateY(8px) scale(1.04)",
      filter: "saturate(1) contrast(1.02) brightness(0.98)",
      transitionTimingFunction: "cubic-bezier(0.33,1,0.68,1)",
    })
    const status = screen.getByText("Ada Lovelace").closest("div")?.parentElement?.parentElement
    expect(status).toBeTruthy()
    const online = document.querySelector(".shadow-glow-green")
    expect(online).toHaveStyle({ right: "4px", bottom: "4px", width: "10px", height: "10px" })
    expect(online?.querySelector(".animate-online-pulse")).toBeInTheDocument()

    expect(screen.getByRole("button", { name: "profile:labels.viewQR" })).toHaveClass(
      "qr-minimal",
      "h-20",
      "w-20",
      "rounded-xl"
    )

    fireEvent.click(screen.getByText("ada@example.com"))
    fireEvent.click(screen.getByText("@ada"))
    fireEvent.click(screen.getByRole("button", { name: "profile:labels.viewQR" }))
    expect(onEmailClick).toHaveBeenCalledOnce()
    expect(onTelegramClick).toHaveBeenCalledOnce()
    expect(onQrClick).toHaveBeenCalledOnce()
  })

  it("uses placeholders for an empty profile and omits optional Telegram status", () => {
    const { container } = render(
      <ProfileHeader {...baseProps} user={null} isOnline={false} reduceMotion />
    )

    expect(screen.getByText("profile:placeholders.status")).toBeInTheDocument()
    expect(screen.getAllByText("—")).toHaveLength(2)
    expect(screen.getByText("profile:placeholders.email")).toBeInTheDocument()
    expect(screen.queryByText("profile:placeholders.telegram")).not.toBeInTheDocument()
    expect(screen.getAllByTestId("profile-smart-image")).toHaveLength(2)
    expect(container.querySelector(".shadow-glow-green")).toBeNull()
    const cover = screen.getAllByTestId("profile-smart-image")[0]?.parentElement
    expect(cover).not.toHaveClass("transition-transform", "duration-hero")
    expect(cover).not.toHaveStyle("transition-timing-function: cubic-bezier(0.33,1,0.68,1)")
    expect(screen.getAllByText("—")[0]).toHaveClass("text-xl", "font-bold", "text-(--brand-main)")

    fireEvent.click(screen.getByRole("button", { name: "profile:labels.viewQR" }))
    expect(baseProps.onQrClick).toHaveBeenCalledOnce()
  })
})
