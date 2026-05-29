import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { Alert, Chip, Avatar, Skeleton, CircularProgress, Snackbar } from "./Feedback"

// Wave 199 SW1 — settings/ui Feedback composite (CONTEXT-tier, no infra).
//
// Compound module: Alert (4 severities) + Chip (3 colors) + Avatar + Skeleton
// (variants) + CircularProgress + Snackbar. All inline (Snackbar is fixed, not a
// portal), no m.*, no network on mount. One composite showcase per theme.
//
// Variants: Default / DarkMode.

const FeedbackComposite = () => (
  <div className="space-y-6">
    <div className="space-y-3">
      <Alert severity="info">Информационное сообщение для пользователя.</Alert>
      <Alert severity="success">Изменения успешно сохранены.</Alert>
      <Alert severity="warning">Проверьте введённые данные перед отправкой.</Alert>
      <Alert severity="error" onClose={() => {}}>
        Не удалось сохранить изменения.
      </Alert>
    </div>
    <div className="flex flex-wrap items-center gap-3">
      <Chip label="Default" />
      <Chip label="Primary" color="primary" />
      <Chip label="Success" color="success" />
      <Avatar src="https://i.pravatar.cc/96?img=12" alt="User avatar" className="h-16 w-16" />
      <CircularProgress />
    </div>
    <div className="flex items-center gap-3">
      <Skeleton variant="circular" width={48} height={48} />
      <div className="flex-1 space-y-2">
        <Skeleton variant="text" width="60%" height={16} />
        <Skeleton variant="rounded" width="100%" height={40} />
      </div>
    </div>
    <Snackbar open onClose={() => {}} anchorOrigin={{ vertical: "bottom", horizontal: "center" }}>
      <Alert severity="success">Профиль обновлён</Alert>
    </Snackbar>
  </div>
)

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div className="settings-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
          <div style={{ width: 520 }}>
            <Story />
          </div>
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof Alert> = {
  title: "Settings/UI/Feedback",
  component: Alert,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
  render: () => <FeedbackComposite />,
}

export default meta
type Story = StoryObj<typeof Alert>

export const Default: Story = { decorators: [themed(false)] }

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
