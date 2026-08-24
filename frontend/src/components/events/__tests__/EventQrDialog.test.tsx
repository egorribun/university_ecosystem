import { fireEvent, render, screen } from "@testing-library/react"
import type { ImgHTMLAttributes } from "react"
import { describe, expect, it, vi } from "vitest"

vi.mock("@/components/ui/Dialog", () => ({
  default: ({ open, children }: { open: boolean; children: React.ReactNode }) =>
    open ? <div role="dialog">{children}</div> : null,
}))

vi.mock("@/components/media/SmartImage", () => ({
  default: (props: ImgHTMLAttributes<HTMLImageElement> & { srcRaw: string }) => {
    const { srcRaw, alt, ...imageProps } = props
    return <img src={srcRaw} alt={alt ?? ""} {...imageProps} />
  },
}))

import { EventQrDialog } from "@/components/events/EventQrDialog"

describe("EventQrDialog", () => {
  it("reveals the QR image after it loads", () => {
    render(<EventQrDialog open qr="ticket:42" onClose={vi.fn()} />)
    const image = screen.getByRole("img")

    expect(image).toHaveClass("opacity-0")
    fireEvent.load(image)
    expect(image).toHaveClass("opacity-100")
  })
})
