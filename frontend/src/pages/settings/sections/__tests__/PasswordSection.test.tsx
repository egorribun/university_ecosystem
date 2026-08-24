import { describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"

import { PasswordSection } from "../PasswordSection"

const baseProps = {
  setSnackbar: vi.fn(),
  currentPasswordValue: "",
  newPasswordValue: "",
  confirmPasswordValue: "",
  currentPasswordError: null,
  passwordError: null,
  isNewPasswordError: false,
  confirmPasswordMessage: null,
  passwordBusy: false,
  onCurrentPasswordChange: vi.fn(),
  onNewPasswordChange: vi.fn(),
  onConfirmPasswordChange: vi.fn(),
  onSubmit: vi.fn<() => Promise<void>>().mockResolvedValue(undefined),
}

describe("PasswordSection", () => {
  it("updates all fields, submits, and exposes busy/error state", async () => {
    const user = userEvent.setup()
    const props = { ...baseProps }
    const { rerender } = render(<PasswordSection {...props} />)

    await user.click(screen.getAllByRole("button")[0]!)
    const fields = screen.getAllByDisplayValue("")
    expect(fields).toHaveLength(3)

    fireEvent.change(fields[0]!, { target: { value: "old-password" } })
    fireEvent.change(fields[1]!, { target: { value: "new-password" } })
    fireEvent.change(fields[2]!, { target: { value: "new-password" } })
    await user.click(screen.getAllByRole("button").at(-1)!)

    expect(props.onCurrentPasswordChange).toHaveBeenCalledWith("old-password")
    expect(props.onNewPasswordChange).toHaveBeenCalledWith("new-password")
    expect(props.onConfirmPasswordChange).toHaveBeenCalledWith("new-password")
    expect(props.onSubmit).toHaveBeenCalledOnce()

    rerender(
      <PasswordSection
        {...props}
        currentPasswordError="Current password is incorrect"
        passwordError="Password is too weak"
        isNewPasswordError
        confirmPasswordMessage="Passwords do not match"
        passwordBusy
      />
    )

    expect(screen.getAllByDisplayValue("")).toHaveLength(3)
    expect(screen.getAllByRole("alert")).toHaveLength(3)
    expect(screen.getAllByRole("button").at(-1)).toBeDisabled()
  })

  it("renders a new-password error state even when no helper message is available", () => {
    render(<PasswordSection {...baseProps} isNewPasswordError passwordError={null} />)

    expect(screen.getAllByDisplayValue("")).toHaveLength(3)
  })
})
