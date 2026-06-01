import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { NewsCardEditDialog, type NewsEditData } from "./NewsCardEditDialog"

// Wave 199 SW1 — NewsCardEditDialog Storybook fixture (CONTEXT-tier, no infra).
//
// Edit form in the @/components/ui Dialog, which renders via createPortal to
// document.body — so the dialog escapes any `.dark` decorator → **default-theme
// only** (EventQrDialog pattern), layout "fullscreen", no DarkMode variant.
// useForm + valibotResolver drive validation locally; image upload + api.patch
// are submit-path only (try/catch), so a static `open` story never hits the
// network on mount. Only useTranslation(["news","common"]) is ambient.
//
// Variants: Default (pre-filled + image) / WithoutImage.

const baseData: NewsEditData = {
  title: "Открыт набор в студенческий совет",
  content: "Подавайте заявки до конца месяца — присоединяйтесь к команде организаторов кампуса.",
  title_en: "Student council applications are open",
  content_en: "Apply by the end of the month and join the campus organising team.",
  image_url: "https://picsum.photos/seed/news-edit/640/360",
}

const withMotion: Decorator = (Story) => (
  <LazyMotion features={domAnimation}>
    <Story />
  </LazyMotion>
)

const meta: Meta<typeof NewsCardEditDialog> = {
  title: "News/NewsCardEditDialog",
  component: NewsCardEditDialog,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
  decorators: [withMotion],
  args: {
    id: "news-1",
    open: true,
    onClose: () => {},
    onSuccess: () => {},
    initialData: baseData,
  },
}

export default meta
type Story = StoryObj<typeof NewsCardEditDialog>

export const Default: Story = {}

export const WithoutImage: Story = {
  args: { initialData: { ...baseData, image_url: "" } },
}
