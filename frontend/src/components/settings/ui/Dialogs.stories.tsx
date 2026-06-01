import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { Button } from "@/components/ui"
import { Dialog, DialogTitle, DialogContent, DialogActions } from "./Dialogs"

// Wave 199 SW1 — settings/ui Dialogs composite (CONTEXT-tier, no infra).
//
// Compound module: Dialog + DialogTitle/Content/Actions. The Dialog renders via
// ReactDOM.createPortal to document.body and animates with framer-motion `m.div`
// → **default-theme only** (portal escapes `.dark`), layout "fullscreen",
// LazyMotion required. No network. One composite "Open" showcase.

const DialogComposite = () => (
  <Dialog open onClose={() => {}} maxWidth="md">
    <DialogTitle>Завершить сессию?</DialogTitle>
    <DialogContent>
      Это действие завершит выбранную сессию на всех устройствах. Вы сможете войти снова в любой
      момент.
    </DialogContent>
    <DialogActions>
      <Button variant="ghost">Отмена</Button>
      <Button variant="solid">Завершить</Button>
    </DialogActions>
  </Dialog>
)

const withMotion: Decorator = (Story) => (
  <LazyMotion features={domAnimation}>
    <Story />
  </LazyMotion>
)

const meta: Meta<typeof Dialog> = {
  title: "Settings/UI/Dialogs",
  component: Dialog,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
  decorators: [withMotion],
  render: () => <DialogComposite />,
}

export default meta
type Story = StoryObj<typeof Dialog>

export const Open: Story = {}
