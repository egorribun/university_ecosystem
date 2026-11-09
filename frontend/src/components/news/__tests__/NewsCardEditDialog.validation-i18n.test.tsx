import { afterEach, describe, expect, it } from "vitest"
import { fireEvent, render, waitFor } from "@testing-library/react"
import { LanguageProvider } from "@/contexts/LanguageContext"
import { NewsCardEditDialog } from "@/components/news/NewsCardEditDialog"

const props = {
  id: "news-validation-locale",
  open: true,
  onClose: () => undefined,
  initialData: {
    title: "Заголовок",
    content: "Текст",
    title_en: "English title",
    content_en: "English text",
    image_url: "",
  },
}

describe("NewsCardEditDialog validation locale", () => {
  afterEach(() => {
    delete window.__UE_SELECTED_LANG__
  })

  it("renders schema validation in the active Russian language provider", async () => {
    window.__UE_SELECTED_LANG__ = "ru"
    localStorage.setItem("ue:language", "ru")
    render(
      <LanguageProvider>
        <NewsCardEditDialog {...props} />
      </LanguageProvider>
    )
    const title = document.querySelector<HTMLInputElement>(
      "#news-edit-title-news-validation-locale"
    )!
    fireEvent.change(title, { target: { value: "" } })
    await waitFor(() => expect(title.parentElement?.querySelector("p")).toBeInTheDocument())
    expect(title.parentElement?.querySelector("p")?.textContent).toBe("Введите заголовок новости")
  })
})
