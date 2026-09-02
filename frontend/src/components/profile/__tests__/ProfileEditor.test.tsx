import { render, screen, fireEvent } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

import { ProfileEditor } from "@/components/profile/ProfileEditor"
import type { User } from "@/types/User"

function makeProps(overrides: Record<string, unknown> = {}) {
  return {
    user: null as User | null,
    fullName: "Ada Lovelace",
    setFullName: vi.fn(),
    email: "ada@example.com",
    setEmail: vi.fn(),
    telegram: "@ada",
    setTelegram: vi.fn(),
    about: "about",
    setAbout: vi.fn(),
    recordBookNumber: "123",
    setRecordBookNumber: vi.fn(),
    status: "active",
    setStatus: vi.fn(),
    institute: "ITM",
    setInstitute: vi.fn(),
    course: "2",
    setCourse: vi.fn(),
    educationLevel: "bachelor",
    setEducationLevel: vi.fn(),
    track: "track",
    setTrack: vi.fn(),
    program: "program",
    setProgram: vi.fn(),
    achievements: "achievements",
    setAchievements: vi.fn(),
    department: "CS",
    setDepartment: vi.fn(),
    position: "prof",
    setPosition: vi.fn(),
    saving: false,
    onSave: vi.fn(),
    onCancel: vi.fn(),
    ...overrides,
  }
}

const teacher = { role: "teacher" } as unknown as User
const student = { role: "student" } as unknown as User

describe("ProfileEditor", () => {
  it("renders base fields and action buttons with no user role", () => {
    render(<ProfileEditor {...makeProps()} />)
    expect(screen.getByText("profile:form.name")).toBeInTheDocument()
    expect(screen.getByText("profile:form.email")).toBeInTheDocument()
    expect(screen.getByText("profile:form.telegram")).toBeInTheDocument()
    expect(screen.getByText("profile:form.save")).toBeInTheDocument()
    expect(screen.getByText("profile:form.cancel")).toBeInTheDocument()
    expect(screen.getByRole("textbox", { name: "profile:form.name" })).toBeInTheDocument()
    expect(screen.getByRole("textbox", { name: "profile:form.email" })).toBeInTheDocument()
    expect(screen.getByRole("textbox", { name: "profile:form.telegram" })).toBeInTheDocument()
    // role-specific fields hidden when no user
    expect(screen.queryByText("profile:form.department")).not.toBeInTheDocument()
    expect(screen.queryByText("profile:form.about")).not.toBeInTheDocument()
    // 3 base textboxes (name, email, telegram)
    expect(screen.getAllByRole("textbox")).toHaveLength(3)
  })

  it("keeps email read-only and fires the editable base-field setters", () => {
    const props = makeProps()
    render(<ProfileEditor {...props} />)
    const boxes = screen.getAllByRole("textbox")
    fireEvent.change(boxes[0]!, { target: { value: "Grace" } })
    fireEvent.change(boxes[1]!, { target: { value: "grace@example.com" } })
    fireEvent.change(boxes[2]!, { target: { value: "@grace" } })
    expect(props.setFullName).toHaveBeenCalledWith("Grace")
    expect(boxes[1]).toHaveValue("ada@example.com")
    expect(boxes[1]).toHaveAttribute("readonly")
    expect(boxes[1]).toHaveAccessibleDescription("profile:form.emailHint")
    expect(props.setEmail).not.toHaveBeenCalled()
    expect(props.setTelegram).toHaveBeenCalledWith("@grace")
    fireEvent.click(screen.getByText("profile:form.save"))
    fireEvent.click(screen.getByText("profile:form.cancel"))
    expect(props.onSave).toHaveBeenCalledOnce()
    expect(props.onCancel).toHaveBeenCalledOnce()
  })

  it("renders teacher fields and wires their setters", () => {
    const props = makeProps({ user: teacher })
    render(<ProfileEditor {...props} />)
    expect(screen.getByText("profile:form.department")).toBeInTheDocument()
    expect(screen.getByText("profile:form.position")).toBeInTheDocument()
    expect(screen.getByRole("textbox", { name: "profile:form.department" })).toBeInTheDocument()
    expect(screen.getByRole("textbox", { name: "profile:form.position" })).toBeInTheDocument()
    const boxes = screen.getAllByRole("textbox")
    boxes.forEach((box, i) => fireEvent.change(box, { target: { value: `v${i}` } }))
    expect(props.setDepartment).toHaveBeenCalled()
    expect(props.setPosition).toHaveBeenCalled()
  })

  it("renders the full student field set and wires every setter", () => {
    const props = makeProps({ user: student })
    render(<ProfileEditor {...props} />)
    for (const key of [
      "profile:form.about",
      "profile:form.recordBookNumber",
      "profile:form.status",
      "profile:form.institute",
      "profile:form.course",
      "profile:form.educationLevel",
      "profile:form.track",
      "profile:form.program",
      "profile:form.achievements",
    ]) {
      expect(screen.getByText(key)).toBeInTheDocument()
      expect(screen.getByRole("textbox", { name: key })).toBeInTheDocument()
    }
    const boxes = screen.getAllByRole("textbox")
    boxes.forEach((box, i) => fireEvent.change(box, { target: { value: `s${i}` } }))
    expect(props.setAbout).toHaveBeenCalled()
    expect(props.setProgram).toHaveBeenCalled()
    expect(props.setAchievements).toHaveBeenCalled()
  })

  it("shows the saving label and disables save while saving", () => {
    render(<ProfileEditor {...makeProps({ saving: true })} />)
    const save = screen.getByText("profile:form.saving")
    expect(save).toBeInTheDocument()
    expect(save).toBeDisabled()
  })
})
