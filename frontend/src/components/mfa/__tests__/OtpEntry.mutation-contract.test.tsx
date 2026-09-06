import type { ReactNode } from "react"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options ? `${key}|${JSON.stringify(options)}` : key,
  }),
}))

vi.mock("@/components/settings", () => ({
  Button: ({
    children,
    onClick,
    disabled,
    loading,
    className,
  }: {
    children: ReactNode
    onClick?: () => void
    disabled?: boolean
    loading?: boolean
    className?: string
  }) => (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={className}
      data-loading={loading ? "true" : "false"}
    >
      {children}
    </button>
  ),
}))

import OtpEntry, { focusOtpInput } from "../OtpEntry"

const inputs = () => screen.getAllByRole("textbox") as HTMLInputElement[]

afterEach(() => vi.restoreAllMocks())

describe("OtpEntry mutation contracts", () => {
  it("fails closed for invalid and not-yet-mounted focus targets", () => {
    const refs: { current: (HTMLInputElement | null)[] } = {
      current: [null, null, null, null, null, null],
    }
    const invalidFocus = vi.fn()

    focusOtpInput(refs, -1)
    focusOtpInput(refs, 6)
    focusOtpInput(refs, 0)
    expect(invalidFocus).not.toHaveBeenCalled()

    refs.current[2] = { focus: invalidFocus } as unknown as HTMLInputElement
    focusOtpInput(refs, 2)
    expect(invalidFocus).toHaveBeenCalledOnce()
  })

  it("keeps the six indexed fields and their stable keys/labels", () => {
    render(<OtpEntry onSubmit={vi.fn()} />)
    const fields = inputs()

    expect(fields).toHaveLength(6)
    fields.forEach((field, index) => {
      expect(field).toHaveAttribute("aria-label", `mfa.otp.methods.totp - digit ${index + 1}`)
      expect(field).toHaveAttribute("type", "text")
      expect(field).toHaveAttribute("inputmode", "numeric")
      expect(field).toHaveAttribute("maxlength", "1")
      expect(field).toHaveAttribute("aria-invalid", "false")
    })
  })

  it("distributes a multi-digit change from the first field and clamps at the end", () => {
    render(<OtpEntry onSubmit={vi.fn()} />)
    const fields = inputs()

    fireEvent.change(fields[0]!, { target: { value: "12x345678" } })
    expect(fields.map((field) => field.value)).toEqual(["1", "2", "3", "4", "5", "6"])
    expect(document.activeElement).toBe(fields[5])

    fireEvent.change(fields[5]!, { target: { value: "98" } })
    expect(fields.map((field) => field.value)).toEqual(["1", "2", "3", "4", "5", "9"])
    expect(document.activeElement).toBe(fields[5])
  })

  it("keeps keyboard navigation within the six-field bounds", () => {
    render(<OtpEntry onSubmit={vi.fn()} />)
    const fields = inputs()

    fields[0]!.focus()
    fireEvent.keyDown(fields[0]!, { key: "ArrowLeft" })
    expect(document.activeElement).toBe(fields[0])
    fireEvent.keyDown(fields[0]!, { key: "Backspace" })
    expect(document.activeElement).toBe(fields[0])

    fields[5]!.focus()
    fireEvent.keyDown(fields[5]!, { key: "ArrowRight" })
    expect(document.activeElement).toBe(fields[5])

    fields[3]!.focus()
    const left = new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true })
    fields[3]!.dispatchEvent(left)
    expect(document.activeElement).toBe(fields[2])
    fields[2]!.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }))
    expect(document.activeElement).toBe(fields[3])
  })

  it("distinguishes incomplete, loading, and server-error submit states", async () => {
    const onSubmit = vi.fn()
    const { rerender } = render(<OtpEntry onSubmit={onSubmit} />)
    const fields = inputs()
    const submit = screen.getByRole("button", { name: "mfa.otp.submit" })

    expect(submit).toBeDisabled()
    fireEvent.change(fields[0]!, { target: { value: "1" } })
    expect(submit).toBeDisabled()

    rerender(<OtpEntry onSubmit={onSubmit} loading />)
    expect(inputs().every((field) => field.disabled)).toBe(true)
    expect(screen.getByRole("button", { name: "mfa.otp.submit" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "mfa.otp.submit" })).toHaveAttribute(
      "data-loading",
      "true"
    )

    rerender(<OtpEntry onSubmit={onSubmit} error="invalid" />)
    expect(screen.getByRole("group")).toHaveAttribute("aria-describedby")
    expect(inputs()[0]).toHaveAttribute("aria-invalid", "true")
    expect(screen.getByText("invalid")).toBeInTheDocument()

    fireEvent.paste(inputs()[0]!, { clipboardData: { getData: () => "123456" } })
    await Promise.resolve()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it("uses exact visual state classes for empty, focused, filled and error digits", async () => {
    const { rerender } = render(<OtpEntry onSubmit={vi.fn()} helperText="hint" />)
    const fields = inputs()

    expect(fields[1]).toHaveClass(
      "w-11",
      "h-14",
      "bg-(--bg-surface-raised)/(--opacity-medium)",
      "border-(--glass-border)/(--opacity-dim)",
      "disabled:cursor-not-allowed"
    )
    fireEvent.focus(fields[1]!)
    expect(fields[1]).toHaveClass("border-(--brand-main)", "scale-105")
    fireEvent.change(fields[1]!, { target: { value: "7" } })
    fireEvent.blur(fields[1]!)
    expect(fields[1]).toHaveClass(
      "border-brand-main/(--opacity-medium)",
      "bg-brand-main/(--opacity-faint)"
    )
    expect(screen.getByText("hint")).toHaveClass("text-xs", "font-bold")

    rerender(<OtpEntry onSubmit={vi.fn()} error="invalid" />)
    await waitFor(() => {
      expect(inputs()[0]).toHaveClass(
        "border-(--error-border)/(--opacity-medium)",
        "focus:border-(--error-border)",
        "focus:ring-4"
      )
    })
    expect(screen.getByText("invalid")).toHaveClass("text-xs", "font-bold", "text-error-text")
  })
})
