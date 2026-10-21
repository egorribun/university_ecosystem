import userEvent from "@testing-library/user-event"
import { expect, vi } from "vitest"

export async function expectImagePickerKeyboard(
  button: HTMLElement,
  input: HTMLInputElement,
  before: HTMLElement,
  after: HTMLElement
): Promise<void> {
  expect(button.tagName).toBe("BUTTON")
  expect(button).toHaveAttribute("type", "button")
  expect(button).toBeEnabled()
  expect(input).toBeEnabled()
  expect(button).not.toContainElement(input)

  const user = userEvent.setup()
  const click = vi.spyOn(input, "click").mockImplementation(() => undefined)
  const restoreGeometry: Array<() => void> = []
  const form = button.closest("form")
  const submit = vi.fn((event: Event) => event.preventDefault())

  try {
    // JSDOM has no layout. Give only this local sequence synthetic geometry;
    // keep the actual dialog/focus-trap implementation and hidden input intact.
    const rect = new DOMRect(0, 0, 100, 44)
    const rects = Object.assign([rect], {
      item: (index: number) => (index === 0 ? rect : null),
    })
    for (const element of [before, button, after]) {
      const spy = vi.spyOn(element, "getClientRects").mockReturnValue(rects)
      restoreGeometry.push(() => spy.mockRestore())
    }
    form?.addEventListener("submit", submit)

    // Awaited interaction allows delayed initial dialog focus to settle.
    await user.click(before)
    expect(before).toHaveFocus()
    await user.tab()
    expect(button).toHaveFocus()
    await user.tab()
    expect(after).toHaveFocus()
    await user.tab({ shift: true })
    expect(button).toHaveFocus()

    await user.keyboard("{Enter}")
    expect(click).toHaveBeenCalledTimes(1)
    await user.keyboard(" ")
    expect(click).toHaveBeenCalledTimes(2)
    await user.click(button)
    expect(click).toHaveBeenCalledTimes(3)
    expect(submit).not.toHaveBeenCalled()
  } finally {
    form?.removeEventListener("submit", submit)
    click.mockRestore()
    restoreGeometry.forEach((restore) => restore())
  }
}
