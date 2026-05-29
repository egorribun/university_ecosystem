import { useState } from "react"
import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import {
  Button,
  Input,
  Textarea,
  SwitchControl,
  RadioGroup,
  Radio,
  FormControlLabel,
  TextField,
} from "./Form"

// Wave 199 SW1 — settings/ui Form composite (CONTEXT-tier, no infra).
//
// Compound module: legacy-compatible Button wrapper + Input/Textarea/TextField +
// SwitchControl + RadioGroup/Radio + FormControlLabel. Inline, no portal, no
// network on mount. Interactive controls (Switch, RadioGroup) use local state in
// the composite harness. LazyMotion wraps in case the underlying primitives use
// motion.
//
// Variants: Default / DarkMode.

const FormComposite = () => {
  const [name, setName] = useState("Егор")
  const [notify, setNotify] = useState(true)
  const [mode, setMode] = useState("system")
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-3">
        <Button variant="solid">Solid</Button>
        <Button variant="outline">Outline</Button>
        <Button variant="ghost">Ghost</Button>
      </div>
      <TextField
        label="Отображаемое имя"
        value={name}
        onChange={(e) => setName(e.target.value)}
        fullWidth
      />
      <Input placeholder="Email" defaultValue="egor@guu.ru" />
      <Textarea placeholder="О себе" rows={3} defaultValue="Студент ГУУ." />
      <FormControlLabel
        control={
          <SwitchControl
            checked={notify}
            onChange={(_, c) => setNotify(c)}
            aria-label="Email notifications"
          />
        }
        label="Уведомления по почте"
      />
      <RadioGroup value={mode} onChange={(_, v) => setMode(v)} className="flex flex-wrap gap-2">
        <FormControlLabel value="system" control={<Radio />} label="Системная" />
        <FormControlLabel value="light" control={<Radio />} label="Светлая" />
        <FormControlLabel value="dark" control={<Radio />} label="Тёмная" />
      </RadioGroup>
    </div>
  )
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div className="settings-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
          <div style={{ width: 480 }}>
            <Story />
          </div>
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof Button> = {
  title: "Settings/UI/Form",
  component: Button,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
  render: () => <FormComposite />,
}

export default meta
type Story = StoryObj<typeof Button>

export const Default: Story = { decorators: [themed(false)] }

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
