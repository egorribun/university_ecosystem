import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"
import OtpEntry from "../OtpEntry"

// Mock translations
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
  useId: () => "test-id",
}))
vi.mock("@/components/settings", () => ({
  Button: ({ children, onClick }: { children: ReactNode; onClick?: () => void }) => (
    <button type="button" onClick={onClick}>
      {children}
    </button>
  ),
}))

describe("OtpEntry", () => {
  it("renders 6 input fields", () => {
    render(<OtpEntry onSubmit={vi.fn()} />)
    const inputs = screen.getAllByRole("textbox")
    expect(inputs).toHaveLength(6)
  })

  it("labels email OTP inputs with the selected verification method", () => {
    render(<OtpEntry method="email_otp" onSubmit={vi.fn()} />)

    expect(screen.getByRole("heading")).toHaveTextContent("mfa.otp.methods.email_otp")
    expect(screen.getByLabelText("mfa.otp.methods.email_otp - digit 1")).toBeInTheDocument()
    expect(screen.getByText("mfa.otp.descriptions.email_otp")).toBeInTheDocument()
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

  it("sanitizes single-digit input, advances focus, and supports clearing", async () => {
    const user = userEvent.setup()
    render(<OtpEntry onSubmit={vi.fn()} />)
    const inputs = screen.getAllByRole("textbox")

    await user.type(inputs[0]!, "a1")
    expect(inputs[0]).toHaveValue("1")
    expect(document.activeElement).toBe(inputs[1])

    await user.clear(inputs[0]!)
    expect(inputs[0]).toHaveValue("")
  })

  it("distributes multi-digit changes across fields and focuses the end", () => {
    render(<OtpEntry onSubmit={vi.fn()} />)
    const inputs = screen.getAllByRole("textbox")

    fireEvent.change(inputs[2]!, { target: { value: "98x7" } })

    expect(inputs.map((input) => (input as HTMLInputElement).value)).toEqual([
      "",
      "",
      "9",
      "8",
      "7",
      "",
    ])
    expect(document.activeElement).toBe(inputs[5])
  })

  it("keeps focus on the final field after a single final digit", () => {
    render(<OtpEntry onSubmit={vi.fn()} />)
    const inputs = screen.getAllByRole("textbox")
    inputs[5]!.focus()

    fireEvent.change(inputs[5]!, { target: { value: "6" } })

    expect(inputs[5]).toHaveValue("6")
    expect(document.activeElement).toBe(inputs[5])
  })

  it("handles backspace and arrow navigation at interior and boundary fields", () => {
    render(<OtpEntry onSubmit={vi.fn()} />)
    const inputs = screen.getAllByRole("textbox")

    inputs[2]!.focus()
    fireEvent.keyDown(inputs[2]!, { key: "Backspace" })
    expect(document.activeElement).toBe(inputs[1])

    inputs[2]!.focus()
    fireEvent.keyDown(inputs[2]!, { key: "ArrowLeft" })
    expect(document.activeElement).toBe(inputs[1])

    fireEvent.keyDown(inputs[1]!, { key: "ArrowRight" })
    expect(document.activeElement).toBe(inputs[2])

    inputs[0]!.focus()
    fireEvent.keyDown(inputs[0]!, { key: "Backspace" })
    fireEvent.keyDown(inputs[5]!, { key: "ArrowRight" })
    expect(document.activeElement).toBe(inputs[0])

    fireEvent.change(inputs[3]!, { target: { value: "7" } })
    fireEvent.keyDown(inputs[3]!, { key: "Backspace" })
    expect(inputs[3]).toHaveValue("7")
  })

  it("ignores a change containing no digits", () => {
    render(<OtpEntry onSubmit={vi.fn()} />)
    const first = screen.getAllByRole("textbox")[0]!

    fireEvent.change(first, { target: { value: "letters-only" } })

    expect(first).toHaveValue("")
  })

  it("handles sanitized paste and ignores an empty paste", () => {
    render(<OtpEntry onSubmit={vi.fn()} />)
    const inputs = screen.getAllByRole("textbox")
    const clipboardData = { getData: () => "a12-3" }

    fireEvent.paste(inputs[0]!, { clipboardData })
    expect(inputs.slice(0, 4).map((input) => (input as HTMLInputElement).value)).toEqual([
      "1",
      "2",
      "3",
      "",
    ])
    expect(document.activeElement).toBe(inputs[2])

    fireEvent.paste(inputs[0]!, { clipboardData: { getData: () => "---" } })
    expect(inputs[0]).toHaveValue("1")
  })

  it("renders helper/error accessibility states and loading affordance", () => {
    const { rerender } = render(
      <OtpEntry onSubmit={vi.fn()} helperText="Use the code from your app" />
    )
    const group = screen.getByRole("group")
    expect(screen.getByText("Use the code from your app")).toBeInTheDocument()
    expect(group).toHaveAttribute("aria-describedby")
    expect(screen.getAllByRole("textbox")[0]).toHaveAttribute("aria-invalid", "false")

    rerender(<OtpEntry onSubmit={vi.fn()} error="Invalid code" />)
    expect(screen.getByText("Invalid code")).toBeInTheDocument()
    expect(screen.getAllByRole("textbox")[0]).toHaveAttribute("aria-invalid", "true")

    rerender(<OtpEntry onSubmit={vi.fn()} loading />)
    expect(document.querySelector(".animate-spin")).toBeInTheDocument()
    expect(screen.getAllByRole("textbox").every((input) => input.hasAttribute("disabled"))).toBe(
      true
    )
  })

  it("clears a partially entered code and restores focus when an error arrives", async () => {
    const { rerender } = render(<OtpEntry onSubmit={vi.fn()} />)
    const inputs = screen.getAllByRole("textbox")

    fireEvent.change(inputs[0]!, { target: { value: "1" } })
    fireEvent.change(inputs[1]!, { target: { value: "2" } })
    expect(inputs.slice(0, 2).map((input) => (input as HTMLInputElement).value)).toEqual(["1", "2"])

    rerender(<OtpEntry onSubmit={vi.fn()} error="Invalid code" />)

    await waitFor(() => {
      expect(inputs.map((input) => (input as HTMLInputElement).value)).toEqual([
        "",
        "",
        "",
        "",
        "",
        "",
      ])
      expect(document.activeElement).toBe(inputs[0])
    })
  })

  it("preserves newly entered digits when the server error is cleared", async () => {
    const onSubmit = vi.fn()
    const { rerender } = render(<OtpEntry onSubmit={onSubmit} />)
    const inputs = screen.getAllByRole("textbox")

    fireEvent.change(inputs[0]!, { target: { value: "1" } })
    rerender(<OtpEntry onSubmit={onSubmit} error="Invalid code" />)
    await waitFor(() => expect(inputs[0]).toHaveValue(""))

    fireEvent.change(inputs[0]!, { target: { value: "7" } })
    rerender(<OtpEntry onSubmit={onSubmit} error={null} />)

    await waitFor(() => expect(inputs[0]).toHaveValue("7"))
  })

  it("returns focus to the first digit after the code is cleared", async () => {
    render(<OtpEntry onSubmit={vi.fn()} />)
    const inputs = screen.getAllByRole("textbox")

    fireEvent.change(inputs[0]!, { target: { value: "1" } })
    inputs[5]!.focus()
    fireEvent.change(inputs[0]!, { target: { value: "" } })

    await waitFor(() => expect(document.activeElement).toBe(inputs[0]))
  })

  it("supports the explicit submit button after a complete code", async () => {
    const onSubmit = vi.fn()
    const user = userEvent.setup()
    render(<OtpEntry onSubmit={onSubmit} />)

    await user.paste("654321")
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith("654321"))
    await user.click(screen.getByRole("button", { name: "mfa.otp.submit" }))

    expect(onSubmit).toHaveBeenCalledTimes(2)
  })

  it("reports the required validation when an incomplete code is submitted", () => {
    render(<OtpEntry onSubmit={vi.fn()} />)
    const submit = screen.getByRole("button", { name: "mfa.otp.submit" })
    submit.removeAttribute("disabled")

    fireEvent.click(submit)

    expect(screen.getByText("mfa.otp.validation.required")).toBeInTheDocument()
  })
})
