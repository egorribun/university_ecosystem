import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

const translationMode = vi.hoisted(() => ({ emptyCopyLabel: false }))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { label?: string }) => {
      if (translationMode.emptyCopyLabel && key === "mfa.totp.copySecret") return null
      return options?.label ? `${key}:${options.label}` : key
    },
  }),
}))

vi.mock("qrcode.react", () => ({
  QRCodeSVG: ({
    value,
    size,
    includeMargin,
    bgColor,
    fgColor,
  }: {
    value: string
    size: number
    includeMargin?: boolean
    bgColor?: string
    fgColor?: string
  }) => (
    <svg
      data-testid="qr-code"
      data-value={value}
      data-size={size}
      data-margin={includeMargin ? "true" : "false"}
      data-bg={bgColor}
      data-fg={fgColor}
    />
  ),
}))

import { TotpQrDisplay } from "../TotpQrDisplay"

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
  translationMode.emptyCopyLabel = false
})

describe("TotpQrDisplay", () => {
  it("normalizes the secret, renders the label, and copies it with feedback", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal("navigator", { clipboard: { writeText } })

    render(
      <TotpQrDisplay
        otpauthUrl="otpauth://totp/Campus"
        secret=" ab cd 12 "
        label="student@example.com"
      />
    )

    expect(screen.getByText("mfa.totp.accountLabel:student@example.com")).toBeInTheDocument()
    expect(screen.getByLabelText("mfa.totp.qrAriaLabel")).toBeInTheDocument()
    expect(document.querySelector(".animate-pulse")).toBeInTheDocument()
    expect(screen.getByDisplayValue("ABCD12")).toBeInTheDocument()
    expect(screen.getByLabelText("mfa.totp.qrAriaLabel")).toHaveClass("min-h-56")

    const qr = await screen.findByTestId("qr-code")
    expect(qr).toHaveAttribute("data-value", "otpauth://totp/Campus")
    expect(qr).toHaveAttribute("data-size", "192")
    expect(qr).toHaveAttribute("data-margin", "true")
    expect(qr).toHaveAttribute("data-bg", "#FFFFFF")
    expect(qr).toHaveAttribute("data-fg", "#0F172A")

    vi.useFakeTimers()
    const button = screen.getByRole("button", { name: "mfa.totp.copySecret" })
    fireEvent.mouseEnter(button)
    expect(screen.getByText("mfa.totp.copySecret")).toBeInTheDocument()
    await act(async () => {
      fireEvent.click(button)
      await Promise.resolve()
    })
    expect(writeText).toHaveBeenCalledWith("ABCD12")
    expect(button).toHaveClass("text-success-text")
    expect(screen.getByText("mfa.totp.copied")).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(2500)
    })
    expect(button).not.toHaveClass("text-success-text")
    fireEvent.mouseLeave(button)
    expect(screen.queryByText("mfa.totp.copySecret")).not.toBeInTheDocument()
  })

  it("clears copied state when the clipboard rejects and supports an absent label", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("clipboard denied"))
    vi.stubGlobal("navigator", { clipboard: { writeText } })

    render(<TotpQrDisplay otpauthUrl="otpauth://totp/NoLabel" secret="xy z" label={null} />)

    expect(screen.queryByText(/mfa\.totp\.accountLabel/)).not.toBeInTheDocument()
    const button = screen.getByRole("button", { name: "mfa.totp.copySecret" })
    fireEvent.click(button)
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("XYZ"))
    expect(button).not.toHaveClass("text-success-text")
  })

  it("removes consecutive whitespace and refreshes the copy callback when the secret changes", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal("navigator", { clipboard: { writeText } })
    const { rerender } = render(
      <TotpQrDisplay otpauthUrl="otpauth://totp/First" secret={"a  \n\t b"} label="" />
    )

    expect(screen.getByDisplayValue("AB")).toBeInTheDocument()
    expect(screen.queryByText(/mfa\.totp\.accountLabel/)).not.toBeInTheDocument()
    rerender(
      <TotpQrDisplay
        otpauthUrl="otpauth://totp/Second"
        secret={"x y" /* pragma: allowlist secret */}
      />
    )
    expect(screen.getByDisplayValue("XY")).toBeInTheDocument()

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "mfa.totp.copySecret" }))
      await Promise.resolve()
    })
    expect(writeText).toHaveBeenCalledWith("XY")
  })

  it("recovers from a clipboard failure after a successful copy", async () => {
    const writeText = vi
      .fn()
      .mockResolvedValueOnce(undefined)
      .mockRejectedValueOnce(new Error("clipboard denied"))
    vi.stubGlobal("navigator", { clipboard: { writeText } })
    render(<TotpQrDisplay otpauthUrl="otpauth://totp/Retry" secret="secret" />)
    const button = screen.getByRole("button", { name: "mfa.totp.copySecret" })

    await act(async () => {
      fireEvent.click(button)
      await Promise.resolve()
    })
    expect(button).toHaveClass("text-success-text")

    await act(async () => {
      fireEvent.click(button)
      await Promise.resolve()
    })
    expect(button).not.toHaveClass("text-success-text")
  })

  it("keeps the copy button usable when the translation is missing", () => {
    translationMode.emptyCopyLabel = true
    render(<TotpQrDisplay otpauthUrl="otpauth://totp/Missing" secret="secret" />)

    expect(document.querySelector("button")).toHaveAttribute("aria-label", "")
  })
})
