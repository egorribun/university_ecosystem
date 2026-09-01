import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const translations: Record<string, string> = {
  "navigation:brandAlt": "GUU logo",
  "navigation:brandName": "GUU Ecosystem",
  "navigation:brandDescription": "Everything you need in one place.",
  "navigation:footer.contactTelegram": "Message us on Telegram",
  "navigation:footer.opensNewTab": "opens in a new tab",
  "navigation:footer.contactEmail": "Send an email",
  "navigation:footer.navigationTitle": "Explore",
  "navigation:footer.profileTitle": "Profile",
  "navigation:footer.myProfile": "My profile",
  "navigation:footer.copyright": "© {{year}} GUU Ecosystem",
  "navigation:footer.careNote": "Created with care for students and staff.",
  "navigation:menu.dashboard": "Dashboard",
  "navigation:menu.news": "News",
  "navigation:menu.schedule": "Schedule",
  "navigation:menu.events": "Events",
  "navigation:menu.map": "Map",
  "navigation:menu.settings": "Settings",
}

const useTranslation = vi.hoisted(() => vi.fn())

vi.mock("react-i18next", () => ({
  useTranslation,
}))

vi.mock("@tanstack/react-router", () => ({
  Link: ({
    to,
    children,
    activeOptions: _activeOptions,
    ...props
  }: {
    to: string
    children: React.ReactNode
    activeOptions?: unknown
  }) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
}))

vi.mock("@/components/media/SmartImage", () => ({
  default: ({
    responsiveWidths,
    srcRaw: _srcRaw,
    alt,
    ...props
  }: { responsiveWidths?: number[]; srcRaw?: string; alt?: string } & Record<string, unknown>) => (
    <img {...props} alt={alt ?? ""} data-responsive-widths={responsiveWidths?.join(",")} />
  ),
}))

import Footer from "@/components/layout/Footer"

describe("Footer mutation contracts", () => {
  beforeEach(() => {
    useTranslation.mockImplementation((_namespaces: string[]) => ({
      t: (key: string, values?: { year?: number }) => {
        const value = translations[key] ?? key
        return values?.year === undefined ? value : value.replace("{{year}}", String(values.year))
      },
    }))
  })

  it("requests the navigation namespace and renders every localized contract", () => {
    render(<Footer />)

    expect(useTranslation).toHaveBeenCalledWith(["navigation"])
    expect(screen.getByRole("heading", { level: 2, name: "GUU Ecosystem" })).toBeInTheDocument()
    expect(screen.getByAltText("GUU logo")).toHaveAttribute("data-responsive-widths", "48,64,96")
    expect(screen.getByText("Everything you need in one place.")).toBeInTheDocument()
    expect(screen.getByRole("heading", { level: 3, name: "Explore" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { level: 3, name: "Profile" })).toBeInTheDocument()
    expect(screen.getByText("Created with care for students and staff.")).toBeInTheDocument()

    for (const [route, label] of [
      ["/dashboard", "Dashboard"],
      ["/news", "News"],
      ["/schedule", "Schedule"],
      ["/events", "Events"],
      ["/map", "Map"],
      ["/profile", "My profile"],
      ["/settings", "Settings"],
    ]) {
      expect(screen.getByRole("link", { name: label })).toHaveAttribute("href", route)
    }

    expect(
      screen.getByRole("link", { name: "Message us on Telegram (opens in a new tab)" })
    ).toHaveAttribute("href", "https://t.me/GUUmsk")
    expect(screen.getByText(`© ${new Date().getFullYear()} GUU Ecosystem`)).toBeInTheDocument()
  })
})
