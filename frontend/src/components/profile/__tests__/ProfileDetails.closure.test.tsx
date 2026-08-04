import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock("@/components/settings", () => ({
  SectionCard: ({ children, ...props }: { children: React.ReactNode }) => <section {...props}>{children}</section>,
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
    render(<ProfileDetails user={null} isOpen={false} onToggle={onToggle} />)
    const toggle = screen.getByRole("button")
    expect(toggle).toHaveAttribute("aria-expanded", "false")
    expect(screen.getAllByTestId("detail-row")).toHaveLength(5)
    expect(screen.getByText("profile:placeholders.about")).toBeInTheDocument()
    fireEvent.click(toggle)
    expect(onToggle).toHaveBeenCalledOnce()
  })

  it("renders teacher department/position and actual about text when open", () => {
    const user = {
      role: "teacher",
      education_path: { institute: "Institute", education_level: "Higher", track: "Track", program: "Program" },
      profile_detail: { department: "Computer Science", position: "Professor", about: "About teacher" },
    } as never
    render(<ProfileDetails user={user} isOpen onToggle={vi.fn()} />)
    const toggle = screen.getByRole("button")
    expect(toggle).toHaveAttribute("aria-expanded", "true")
    expect(screen.getByText("profile:labels.department:Computer Science")).toBeInTheDocument()
    expect(screen.getByText("profile:labels.position:Professor")).toBeInTheDocument()
    expect(screen.getByText("About teacher")).toBeInTheDocument()
  })
})
