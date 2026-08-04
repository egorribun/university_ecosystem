import { act, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/components/media/SmartImage", () => ({
  default: ({
    srcRaw,
    ...props
  }: { srcRaw: string } & React.ImgHTMLAttributes<HTMLImageElement>) => (
    <img src={srcRaw} alt={props.alt ?? ""} {...props} />
  ),
}))

import { Alert, Avatar, Chip, CircularProgress, Skeleton, Snackbar } from "../Feedback"

describe("Feedback primitives", () => {
  it("renders every alert severity and optional close action", () => {
    const onClose = vi.fn()

    for (const severity of ["info", "error", "warning", "success"] as const) {
      const { unmount } = render(
        <Alert severity={severity} onClose={onClose}>
          {severity} message
        </Alert>
      )
      expect(screen.getByRole("alert")).toHaveTextContent(`${severity} message`)
      fireEvent.click(screen.getByRole("button"))
      unmount()
    }

    render(<Alert>without close</Alert>)
    expect(screen.queryByRole("button")).not.toBeInTheDocument()
    expect(onClose).toHaveBeenCalledTimes(4)
  })

  it("renders chips, avatars, and circular progress with forwarded props", () => {
    render(
      <>
        <Chip label="Default" />
        <Chip label="Success" color="success" data-testid="success-chip" />
        <Chip label="Primary" color="primary" className="extra" />
        <Avatar
          src="/avatar.png"
          alt="Profile avatar"
          imgProps={{ loading: "lazy", decoding: "async" }}
        />
        <CircularProgress size={32} className="custom-progress" />
      </>
    )

    expect(screen.getByText("Default")).toBeInTheDocument()
    expect(screen.getByTestId("success-chip")).toHaveTextContent("Success")
    expect(screen.getByText("Primary")).toHaveClass("extra")
    expect(screen.getByRole("img", { name: "Profile avatar" })).toHaveAttribute(
      "src",
      "/avatar.png"
    )
    expect(screen.getByRole("img", { name: "Profile avatar" })).toHaveAttribute("loading", "lazy")
    expect(document.querySelector(".custom-progress")).toHaveAttribute("width", "32")
  })

  it("renders skeleton variants and normalizes numeric dimensions", () => {
    const { container } = render(
      <>
        <Skeleton variant="circular" width={16} height={24} />
        <Skeleton variant="rounded" width="50%" height="2rem" />
        <Skeleton variant="text" style={{ opacity: 0.5 }} />
        <Skeleton variant="rectangular" />
      </>
    )

    const skeletons = Array.from(container.querySelectorAll(".animate-pulse"))
    expect(skeletons).toHaveLength(4)
    expect(skeletons[0]).toHaveStyle({ width: "1rem", height: "1.5rem" })
    expect(skeletons[1]).toHaveStyle({ width: "50%", height: "2rem" })
    expect(skeletons[2]).toHaveStyle({ opacity: "0.5" })
  })

  describe("Snackbar", () => {
    beforeEach(() => {
      vi.useFakeTimers()
    })

    afterEach(() => {
      vi.useRealTimers()
    })

    it("returns nothing while closed and positions an open snackbar", () => {
      const { container, rerender } = render(
        <Snackbar open={false} onClose={vi.fn()}>
          Hidden
        </Snackbar>
      )
      expect(container).toBeEmptyDOMElement()

      rerender(
        <Snackbar
          open
          onClose={vi.fn()}
          anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
          className="toast"
        >
          Bottom
        </Snackbar>
      )
      expect(screen.getByText("Bottom")).toHaveClass("bottom-8", "left-1/2", "toast")

      rerender(
        <Snackbar open onClose={vi.fn()} anchorOrigin={{ vertical: "top", horizontal: "right" }}>
          Top
        </Snackbar>
      )
      expect(screen.getByText("Top")).toHaveClass("top-8", "right-8")

      rerender(<Snackbar open onClose={vi.fn()} />)
      expect(container.firstElementChild).toHaveClass("top-1/2", "left-8")
    })

    it("auto-closes after the configured duration and cleans up on rerender", () => {
      const onClose = vi.fn()
      const { rerender } = render(
        <Snackbar open onClose={onClose} autoHideDuration={1000}>
          Timed
        </Snackbar>
      )

      act(() => {
        vi.advanceTimersByTime(999)
      })
      expect(onClose).not.toHaveBeenCalled()
      act(() => {
        vi.advanceTimersByTime(1)
      })
      expect(onClose).toHaveBeenCalledOnce()

      const secondClose = vi.fn()
      rerender(
        <Snackbar open onClose={secondClose} autoHideDuration={1000}>
          Replaced
        </Snackbar>
      )
      rerender(<Snackbar open={false} onClose={secondClose} autoHideDuration={1000} />)
      act(() => {
        vi.advanceTimersByTime(1000)
      })
      expect(secondClose).not.toHaveBeenCalled()
    })
  })
})
