import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

const translationNamespaces: unknown[] = []
vi.mock("react-i18next", () => ({
  useTranslation: (namespaces?: unknown) => {
    translationNamespaces.push(namespaces)
    return { t: (key: string) => key }
  },
}))

vi.mock("@/components/settings", () => ({
  SectionCard: ({ children, ...props }: { children: React.ReactNode }) => (
    <section {...props}>{children}</section>
  ),
  Divider: () => <hr />,
}))

vi.mock("../DetailRow", () => ({
  default: ({ label, value }: { label: string; value?: React.ReactNode }) => (
    <div data-testid="detail-row">
      {label}:{value}
    </div>
  ),
}))

import ProfileDetails from "../ProfileDetails"

describe("ProfileDetails role and disclosure branches", () => {
  it("renders collapsed student details and placeholder text", () => {
    const onToggle = vi.fn()
    const { container } = render(<ProfileDetails user={null} isOpen={false} onToggle={onToggle} />)
    const toggle = screen.getByRole("button")
    expect(toggle).toHaveAttribute("aria-expanded", "false")
    expect(translationNamespaces).toContainEqual(["profile"])
    expect(container.querySelector("section")).toHaveClass(
      "p-0",
      "border-none",
      "bg-(--bg-surface)/(--opacity-subtle)",
      "rounded-3xl",
      "overflow-hidden"
    )
    expect(toggle).toHaveClass("mt-(--space-4)", "relative", "px-6", "py-5", "focus-visible:ring-2")
    expect(toggle.querySelector("svg")).not.toHaveClass("rotate-180")
    const content = container.querySelector(".grid") as HTMLElement
    expect(content.style.gridTemplateRows).toBe("0fr")
    expect(content.style.opacity).toBe("0")
    expect(screen.getAllByTestId("detail-row")).toHaveLength(5)
    expect(screen.getByText("profile:placeholders.about")).toBeInTheDocument()
    fireEvent.click(toggle)
    expect(onToggle).toHaveBeenCalledOnce()
  })

  it("renders teacher department/position and actual about text when open", () => {
    const user = {
      role: "teacher",
      education_path: {
        institute: "Institute",
        education_level: "Higher",
        track: "Track",
        program: "Program",
      },
      profile_detail: {
        department: "Computer Science",
        position: "Professor",
        about: "About teacher",
      },
    } as never
    const { container } = render(<ProfileDetails user={user} isOpen onToggle={vi.fn()} />)
    const toggle = screen.getByRole("button")
    expect(toggle).toHaveAttribute("aria-expanded", "true")
    expect(toggle.querySelector("svg")).toHaveClass("rotate-180")
    const content = container.querySelector(".grid") as HTMLElement
    expect(content.style.gridTemplateRows).toBe("1fr")
    expect(content.style.opacity).toBe("1")
    expect(screen.getByText("profile:labels.department:Computer Science")).toBeInTheDocument()
    expect(screen.getByText("profile:labels.position:Professor")).toBeInTheDocument()
    expect(screen.getByText("About teacher")).toBeInTheDocument()
  })

  it("uses student track/program values and the about placeholder", () => {
    const user = {
      role: "student",
      education_path: {
        institute: "Institute",
        education_level: "Bachelor",
        track: "Software",
        program: "Computer Science",
      },
      profile_detail: {},
    } as never
    render(<ProfileDetails user={user} isOpen onToggle={() => {}} />)

    expect(screen.getByText("profile:labels.track:Software")).toBeInTheDocument()
    expect(screen.getByText("profile:labels.program:Computer Science")).toBeInTheDocument()
    expect(screen.getByText("profile:placeholders.about")).toBeInTheDocument()
  })
})
