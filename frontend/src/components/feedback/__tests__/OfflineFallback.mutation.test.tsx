import { createElement, type ReactNode } from "react"
import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const state = vi.hoisted(() => ({
  navigate: vi.fn(),
  t: vi.fn((key: string) => key),
  useTranslation: vi.fn(),
}))

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => state.navigate,
}))

vi.mock("react-i18next", () => ({
  useTranslation: state.useTranslation,
}))

vi.mock("lucide-react", () => ({
  WifiOff: ({ size }: { size?: number }) => (
    <svg data-testid="offline-fallback-wifi" data-size={size} aria-hidden="true" />
  ),
  Home: ({ size }: { size?: number }) => (
    <svg data-testid="offline-fallback-home" data-size={size} aria-hidden="true" />
  ),
  RotateCw: ({ size }: { size?: number }) => (
    <svg data-testid="offline-fallback-refresh" data-size={size} aria-hidden="true" />
  ),
}))

vi.mock("framer-motion", () => {
  const motion = (tag: string) => {
    const Component = ({
      children,
      initial,
      animate,
      transition,
      ...props
    }: {
      children?: ReactNode
      initial?: Record<string, unknown>
      animate?: Record<string, unknown>
      transition?: Record<string, unknown>
      className?: string
    }) =>
      createElement(
        tag,
        {
          ...props,
          "data-motion-tag": tag,
          "data-motion-initial": JSON.stringify(initial),
          "data-motion-animate": JSON.stringify(animate),
          "data-motion-transition": JSON.stringify(transition),
        },
        children
      )
    Component.displayName = `Motion${tag}`
    return Component
  }

  return {
    m: {
      div: motion("div"),
      h1: motion("h1"),
      p: motion("p"),
    },
  }
})

import OfflineFallback from "@/components/feedback/OfflineFallback"

function motionProps(element: HTMLElement) {
  return {
    initial: JSON.parse(element.dataset.motionInitial ?? "null"),
    animate: JSON.parse(element.dataset.motionAnimate ?? "null"),
    transition: JSON.parse(element.dataset.motionTransition ?? "null"),
  }
}

describe("OfflineFallback mutation contracts", () => {
  beforeEach(() => {
    state.navigate.mockReset()
    state.t.mockReset().mockImplementation((key: string) => key)
    state.useTranslation.mockReset().mockReturnValue({ t: state.t })
  })

  it("preserves the exact translated content and motion contracts for every section", () => {
    render(<OfflineFallback />)

    expect(state.useTranslation).toHaveBeenCalledWith("system")
    expect(state.t).toHaveBeenCalledWith("offlineFallback.title")
    expect(state.t).toHaveBeenCalledWith("offlineFallback.description")
    expect(state.t).toHaveBeenCalledWith("offlineFallback.retry")
    expect(state.t).toHaveBeenCalledWith("offlineFallback.backHome")

    const motionDivs = Array.from(document.querySelectorAll<HTMLElement>('[data-motion-tag="div"]'))
    expect(motionDivs).toHaveLength(2)
    expect(motionProps(motionDivs[0]!)).toEqual({
      initial: { scale: 0.8, opacity: 0 },
      animate: { scale: 1, opacity: 1 },
      transition: { type: "spring", stiffness: 200, damping: 20 },
    })
    expect(motionProps(screen.getByRole("heading", { name: "offlineFallback.title" }))).toEqual({
      initial: { y: 20, opacity: 0 },
      animate: { y: 0, opacity: 1 },
      transition: { delay: 0.1 },
    })
    expect(motionProps(screen.getByText("offlineFallback.description"))).toEqual({
      initial: { y: 20, opacity: 0 },
      animate: { y: 0, opacity: 1 },
      transition: { delay: 0.2 },
    })
    expect(motionProps(motionDivs[1]!)).toEqual({
      initial: { y: 20, opacity: 0 },
      animate: { y: 0, opacity: 1 },
      transition: { delay: 0.3 },
    })

    expect(motionDivs[0]).toHaveClass(
      "mb-8",
      "flex",
      "h-24",
      "w-24",
      "items-center",
      "justify-center",
      "rounded-full",
      "bg-warning-bg/(--opacity-dim)",
      "text-warning-text"
    )
    expect(screen.getByTestId("offline-fallback-wifi")).toHaveAttribute("data-size", "48")
    expect(screen.getByRole("heading")).toHaveClass(
      "mb-4",
      "text-2xl",
      "font-bold",
      "tracking-tight",
      "text-text-primary",
      "sm:text-3xl"
    )
    expect(screen.getByText("offlineFallback.description")).toHaveClass(
      "mb-10",
      "max-w-[28rem]",
      "leading-relaxed",
      "text-(--text-secondary)"
    )
    expect(motionDivs[1]).toHaveClass("flex", "flex-col", "gap-3", "sm:flex-row")
  })

  it("runs the supplied retry callback and navigates home with distinct button contracts", () => {
    const onRetry = vi.fn()
    render(<OfflineFallback onRetry={onRetry} />)

    const retry = screen.getByRole("button", { name: "offlineFallback.retry" })
    const backHome = screen.getByRole("button", { name: "offlineFallback.backHome" })
    expect(retry).toHaveClass("bg-linear-brand", "shadow-surface", "ring-brand/(--opacity-dim)")
    expect(backHome).toHaveClass("border", "border-white/(--opacity-subtle)")
    expect(screen.getByTestId("offline-fallback-refresh")).toHaveAttribute("data-size", "18")
    expect(screen.getByTestId("offline-fallback-home")).toHaveAttribute("data-size", "18")

    fireEvent.click(retry)
    expect(onRetry).toHaveBeenCalledOnce()
    fireEvent.click(backHome)
    expect(state.navigate).toHaveBeenCalledWith({ to: "/" })
  })
})
