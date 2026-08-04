import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { EmailSection } from "../EmailSection"

const baseProps = {
  setSnackbar: vi.fn(),
  emailValue: "old@example.com",
  emailPassword: "old-password",
  emailBusy: false,
  emailError: null,
  emailPasswordError: null,
  pendingEmail: "pending@example.com",
  onEmailChange: vi.fn(),
  onPasswordChange: vi.fn(),
  onSubmit: vi.fn<() => Promise<void>>().mockResolvedValue(undefined),
}

describe("EmailSection", () => {
  it("updates both fields, submits, and exposes pending/error/busy state", async () => {
    const user = userEvent.setup()
    const props = { ...baseProps }
    const { rerender } = render(<EmailSection {...props} />)

    await user.click(screen.getAllByRole("button")[0]!)
    const fields = [
      screen.getByDisplayValue("old@example.com"),
      screen.getByDisplayValue("old-password"),
    ]
    expect(fields).toHaveLength(2)

    fireEvent.change(fields[0], { target: { value: "new@example.com" } })
    fireEvent.change(fields[1], { target: { value: "current-password" } })
    await user.click(screen.getAllByRole("button").at(-1)!)

    expect(props.onEmailChange).toHaveBeenCalledWith("new@example.com")
    expect(props.onPasswordChange).toHaveBeenCalledWith("current-password")
    expect(props.onSubmit).toHaveBeenCalledOnce()
    expect(screen.getByRole("alert")).toHaveTextContent("pending@example.com")

    rerender(
      <EmailSection
        {...props}
        emailError="Email is invalid"
        emailPasswordError="Password is incorrect"
        emailBusy
      />
    )

    expect(screen.getAllByRole("alert")).toHaveLength(3)
    expect(screen.getByDisplayValue("old@example.com")).toBeDisabled()
    expect(screen.getByDisplayValue("old-password")).toBeDisabled()
    expect(screen.getAllByRole("button").at(-1)).toBeDisabled()
  })
})
