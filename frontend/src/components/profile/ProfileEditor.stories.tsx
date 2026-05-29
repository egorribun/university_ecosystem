import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { useState } from "react"
import type { User } from "@/types/User"
import { ProfileEditor } from "./ProfileEditor"

// Wave 198 SW6 — ProfileEditor Storybook fixture (profile, pure-props).
//
// Controlled edit form — ~30 value+setter props. A local-useState harness makes
// the inputs interactive without external state. The visible field set switches on
// user.role ("student" → about/record-book/.../achievements; "teacher" →
// department/position). No network, no m.*. Scoped in `.profile-theme`.
//
// Variants: Student / Teacher / DarkMode.

const noop = () => {}

function ProfileEditorHarness({
  userRole,
  saving = false,
}: {
  userRole: "student" | "teacher"
  saving?: boolean
}) {
  const [fullName, setFullName] = useState("Alice Anderson")
  const [email, setEmail] = useState("alice@university.dev")
  const [telegram, setTelegram] = useState("@alice")
  const [about, setAbout] = useState("Second-year CS student interested in distributed systems.")
  const [recordBookNumber, setRecordBookNumber] = useState("21-1042")
  const [status, setStatus] = useState("Active")
  const [institute, setInstitute] = useState("Institute of Information Systems")
  const [course, setCourse] = useState("2")
  const [educationLevel, setEducationLevel] = useState("Bachelor")
  const [track, setTrack] = useState("Software Engineering")
  const [program, setProgram] = useState("09.03.04")
  const [achievements, setAchievements] = useState("Dean's list 2025")
  const [department, setDepartment] = useState("Department of Software Engineering")
  const [position, setPosition] = useState("Associate Professor")
  const user = { role: userRole } as unknown as User

  return (
    <ProfileEditor
      user={user}
      fullName={fullName}
      setFullName={setFullName}
      email={email}
      setEmail={setEmail}
      telegram={telegram}
      setTelegram={setTelegram}
      about={about}
      setAbout={setAbout}
      recordBookNumber={recordBookNumber}
      setRecordBookNumber={setRecordBookNumber}
      status={status}
      setStatus={setStatus}
      institute={institute}
      setInstitute={setInstitute}
      course={course}
      setCourse={setCourse}
      educationLevel={educationLevel}
      setEducationLevel={setEducationLevel}
      track={track}
      setTrack={setTrack}
      program={program}
      setProgram={setProgram}
      achievements={achievements}
      setAchievements={setAchievements}
      department={department}
      setDepartment={setDepartment}
      position={position}
      setPosition={setPosition}
      saving={saving}
      onSave={noop}
      onCancel={noop}
    />
  )
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div className="profile-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div style={{ width: 540, maxWidth: "100%" }}>
          <Story />
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof ProfileEditor> = {
  title: "Profile/ProfileEditor",
  component: ProfileEditor,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof ProfileEditor>

export const Student: Story = {
  render: () => <ProfileEditorHarness userRole="student" />,
  decorators: [themed(false)],
}

export const Teacher: Story = {
  render: () => <ProfileEditorHarness userRole="teacher" />,
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  render: () => <ProfileEditorHarness userRole="student" />,
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
