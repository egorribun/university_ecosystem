import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi } from "vitest"

const translationState = vi.hoisted(() => ({ returnUndefined: false }))
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => (translationState.returnUndefined ? undefined : key),
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

import { NewsCardActions } from "@/components/news/NewsCardActions"

function setup(overrides: Partial<Parameters<typeof NewsCardActions>[0]> = {}) {
  const onEdit = vi.fn()
  const onDelete = vi.fn()
  render(<NewsCardActions id="article-7" onEdit={onEdit} onDelete={onDelete} {...overrides} />)
  return { onEdit, onDelete }
}

describe("NewsCardActions", () => {
  it("renders the menu trigger closed by default", () => {
    setup()
    const trigger = screen.getByRole("button", { name: "news:aria.cardActions" })
    expect(trigger).toBeInTheDocument()
    expect(trigger).toHaveAttribute("aria-haspopup", "true")
    expect(trigger).not.toHaveAttribute("aria-expanded")
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
  })

  it("opens the dropdown menu when the trigger is clicked", async () => {
    const user = userEvent.setup()
    setup()
    await user.click(screen.getByRole("button", { name: "news:aria.cardActions" }))
    expect(screen.getByRole("menu")).toBeInTheDocument()
    expect(screen.getByText("common:buttons.edit")).toBeInTheDocument()
    expect(screen.getByText("common:buttons.delete")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "news:aria.cardActions" })).toHaveAttribute(
      "aria-expanded",
      "true"
    )
  })

  it("invokes onEdit and closes the menu when Edit is clicked", async () => {
    const user = userEvent.setup()
    const { onEdit, onDelete } = setup()
    await user.click(screen.getByRole("button", { name: "news:aria.cardActions" }))
    await user.click(screen.getByText("common:buttons.edit"))
    expect(onEdit).toHaveBeenCalledTimes(1)
    expect(onDelete).not.toHaveBeenCalled()
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
  })

  it("invokes onDelete and closes the menu when Delete is clicked", async () => {
    const user = userEvent.setup()
    const { onEdit, onDelete } = setup()
    await user.click(screen.getByRole("button", { name: "news:aria.cardActions" }))
    await user.click(screen.getByText("common:buttons.delete"))
    expect(onDelete).toHaveBeenCalledTimes(1)
    expect(onEdit).not.toHaveBeenCalled()
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
  })

  it("closes the menu when Escape is pressed", async () => {
    const user = userEvent.setup()
    setup()
    await user.click(screen.getByRole("button", { name: "news:aria.cardActions" }))
    expect(screen.getByRole("menu")).toBeInTheDocument()
    await user.keyboard("{Escape}")
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
  })

  it("keeps the menu open for unrelated keys", async () => {
    const user = userEvent.setup()
    setup()
    await user.click(screen.getByRole("button", { name: "news:aria.cardActions" }))

    await user.keyboard("{Tab}")

    expect(screen.getByRole("menu")).toBeInTheDocument()
  })

  it("closes the menu when the pointer lands outside the menu", async () => {
    const user = userEvent.setup()
    setup()
    await user.click(screen.getByRole("button", { name: "news:aria.cardActions" }))
    expect(screen.getByRole("menu")).toBeInTheDocument()

    await user.click(document.body)
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
  })

  it("falls back to an empty aria-label when the translation is unavailable", () => {
    translationState.returnUndefined = true
    try {
      const { container } = render(
        <NewsCardActions id="article-undefined" onEdit={vi.fn()} onDelete={vi.fn()} />
      )
      expect(container.querySelector("[data-news-card-menu-button]")).toHaveAttribute(
        "aria-label",
        ""
      )
    } finally {
      translationState.returnUndefined = false
    }
  })

  it("disables the trigger and ignores clicks when isDisabled is set", async () => {
    const user = userEvent.setup()
    setup({ isDisabled: true })
    const trigger = screen.getByRole("button", { name: "news:aria.cardActions" })
    expect(trigger).toBeDisabled()
    await user.click(trigger)
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
  })

  it("derives stable element ids from the article id", () => {
    setup({ id: "xyz" })
    expect(screen.getByRole("button", { name: "news:aria.cardActions" })).toHaveAttribute(
      "id",
      "news-card-menu-xyz-button"
    )
  })

  it("stops clicks on the action container from reaching the card", () => {
    const onCardClick = vi.fn()
    const outer = document.createElement("div")
    const reactRoot = document.createElement("div")
    outer.append(reactRoot)
    document.body.append(outer)
    outer.addEventListener("click", onCardClick)
    const { container, unmount } = render(
      <NewsCardActions id="article-stop" onEdit={vi.fn()} onDelete={vi.fn()} />,
      { container: reactRoot }
    )

    const actionContainer = container.querySelector('[role="presentation"]')
    expect(actionContainer).not.toBeNull()
    fireEvent.click(actionContainer!)

    expect(onCardClick).not.toHaveBeenCalled()
    unmount()
    outer.remove()
  })
})
