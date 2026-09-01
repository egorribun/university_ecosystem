import { screen, render } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("@/components/ui/motion/FadeIn", () => ({
  FadeIn: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <div data-testid="login-hero-fade" className={className}>
      {children}
    </div>
  ),
}))

import { LoginHero } from "./LoginHero"

describe("LoginHero", () => {
  it("renders the complete localized hero content and all product highlights", () => {
    const { container } = render(<LoginHero />)

    expect(screen.getByText("University Ecosystem")).toBeInTheDocument()
    expect(
      screen.getByRole("heading", { name: "Welcome to the University system" })
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        "Schedule, news, events, and messenger — all in one place for students and professors."
      )
    ).toBeInTheDocument()

    expect(screen.getByText("Class schedule")).toBeInTheDocument()
    expect(
      screen.getByText("Up-to-date schedule of classes, exams, and consultations.")
    ).toBeInTheDocument()
    expect(screen.getByText("News and events")).toBeInTheDocument()
    expect(
      screen.getByText("Stay up to date with university life and important events.")
    ).toBeInTheDocument()
    expect(screen.getByText("Messenger")).toBeInTheDocument()
    expect(screen.getByText("Chat with classmates and professors.")).toBeInTheDocument()

    const cards = container.querySelectorAll(".auth-perk-card")
    expect(cards).toHaveLength(3)
    expect(cards[0]?.querySelector("svg")).toHaveClass("lucide-calendar")
    expect(cards[1]?.querySelector("svg")).toHaveClass("lucide-newspaper")
    expect(cards[2]?.querySelector("svg")).toHaveClass("lucide-message-circle")

    expect(screen.getByText("Fast")).toBeInTheDocument()
    expect(screen.getByText("and secure")).toBeInTheDocument()
    expect(screen.getByText("Smart interface")).toBeInTheDocument()
    expect(screen.getByTestId("login-hero-fade")).toHaveClass(
      "auth-card-glass",
      "flex",
      "w-full",
      "min-w-0"
    )
  })
})
