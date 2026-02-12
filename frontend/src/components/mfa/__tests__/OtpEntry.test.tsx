import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import OtpEntry from "../OtpEntry"

// Mock translations
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
  useId: () => "test-id",
}))

describe("OtpEntry", () => {
  it("renders 6 input fields", () => {
    render(<OtpEntry onSubmit={vi.fn()} />)
    const inputs = screen.getAllByRole("textbox")
    expect(inputs).toHaveLength(6)
  })

  it("calls onSubmit automatically when 6 digits are entered", async () => {
    const onSubmit = vi.fn()
    const user = userEvent.setup()
    render(<OtpEntry onSubmit={onSubmit} />)

    // Simulate typing 6 digits
    // Note: We need to type into the first input, or handle how the component distributes focus
    // The component manages focus, but for userEvent we might need to be careful
    // Let's try typing into the first one and see if it propagates or just type one by one if needed.
    // However, fast typing or pasting is handled.
    // Let's paste the whole code.

    await user.paste("123456")

    // The component has a delay or effect tick, so we wait
    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith("123456")
    })
  })

  it("does not call onSubmit if less than 6 digits are entered", async () => {
    const onSubmit = vi.fn()
    const user = userEvent.setup()
    render(<OtpEntry onSubmit={onSubmit} />)

    await user.paste("12345")

    // Wait a bit to ensure it doesn't fire
    await new Promise((r) => setTimeout(r, 100))
    expect(onSubmit).not.toHaveBeenCalled()
  })
})
