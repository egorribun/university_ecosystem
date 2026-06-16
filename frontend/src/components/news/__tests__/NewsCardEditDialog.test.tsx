import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

import { NewsCardEditDialog, type NewsEditData } from "@/components/news/NewsCardEditDialog"

const initialData: NewsEditData = {
  title: "Открыт набор в студенческий совет",
  content: "Подавайте заявки до конца месяца.",
  title_en: "Student council applications are open",
  content_en: "Apply by the end of the month.",
  image_url: "https://picsum.photos/seed/news-edit/640/360",
}

const baseProps = {
  id: "news-1",
  open: true,
  onClose: vi.fn(),
  initialData,
  onSuccess: vi.fn(),
}

describe("NewsCardEditDialog", () => {
  it("renders the dialog with prefilled fields when open", () => {
    render(<NewsCardEditDialog {...baseProps} />)
    expect(screen.getByText("news:dialogs.edit.title")).toBeInTheDocument()
    expect(screen.getByDisplayValue(initialData.title)).toBeInTheDocument()
    expect(screen.getByDisplayValue(initialData.content)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "common:buttons.save" })).toBeInTheDocument()
  })

  it("does not render the dialog body when closed", () => {
    render(<NewsCardEditDialog {...baseProps} open={false} />)
    expect(screen.queryByText("news:dialogs.edit.title")).not.toBeInTheDocument()
  })

  it("fires onClose from the cancel button", async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<NewsCardEditDialog {...baseProps} onClose={onClose} />)
    await user.click(screen.getByRole("button", { name: "common:buttons.cancel" }))
    expect(onClose).toHaveBeenCalledOnce()
  })
})
