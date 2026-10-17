import { act, cleanup, render, screen } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { startTotpEnrollment } from "@/api/mfa"

const qrModule = vi.hoisted(() => {
  let release!: () => void
  const ready = new Promise<void>((resolve) => {
    release = resolve
  })
  return { ready, release }
})

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))
vi.mock("qrcode.react", async () => {
  await qrModule.ready
  return { QRCodeSVG: () => <svg data-testid="loaded-qr" /> }
})

import { TotpQrDisplay } from "../TotpQrDisplay"

it("keeps the QR placeholder until its lazy module loads", async () => {
  try {
    const enrollment = await startTotpEnrollment({ label: "QR loading fixture" })
    render(
      <TotpQrDisplay
        otpauthUrl={enrollment.otpauth_url}
        secret={enrollment.secret}
        label={enrollment.enrollment.label}
      />
    )
    const frame = screen.getByLabelText("mfa.totp.qrAriaLabel")
    expect(frame.querySelector(".animate-pulse")).toBeInTheDocument()
    expect(screen.queryByTestId("loaded-qr")).not.toBeInTheDocument()

    await act(async () => {
      qrModule.release()
      await vi.dynamicImportSettled()
    })
    expect(screen.getByTestId("loaded-qr")).toBeInTheDocument()
    expect(frame.querySelector(".animate-pulse")).not.toBeInTheDocument()
  } finally {
    try {
      await act(async () => {
        qrModule.release()
        await vi.dynamicImportSettled()
      })
    } finally {
      cleanup()
    }
  }
})
