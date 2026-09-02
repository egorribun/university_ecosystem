import { render, fireEvent } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import type { ComponentProps, ReactNode } from "react"

import { ProfileModal } from "@/components/messenger/ProfileModal"

const mocks = vi.hoisted(() => ({
  motion: vi.fn(),
  translation: vi.fn(),
  mediaQuery: vi.fn(() => false),
  focusTrap: vi.fn(() => ({ current: null })),
}))

vi.mock("framer-motion", () => {
  const createMotionElement = (tag: "div" | "button") => {
    const Component = ({ children, ...props }: Record<string, unknown>) => {
      mocks.motion(tag, props)
      const domProps = Object.fromEntries(
        Object.entries(props).filter(
          ([key]) =>
            !["initial", "animate", "exit", "transition", "whileHover", "whileTap"].includes(key)
        )
      )
      return (
        <>
          {tag === "div" ? (
            <div {...domProps}>{children as ReactNode}</div>
          ) : (
            <button {...domProps}>{children as ReactNode}</button>
          )}
        </>
      )
    }
    Component.displayName = `Motion(${tag})`
    return Component
  }
  return {
    AnimatePresence: ({ children }: { children: ReactNode }) => <>{children}</>,
    m: { div: createMotionElement("div"), button: createMotionElement("button") },
  }
})

vi.mock("react-i18next", () => ({
  useTranslation: (...args: unknown[]) => {
    mocks.translation(...args)
    return { t: (key: string) => key }
  },
}))

vi.mock("@/hooks/useMediaQuery", () => ({ default: mocks.mediaQuery }))
vi.mock("@/hooks/useFocusTrap", () => ({ default: mocks.focusTrap }))
vi.mock("@/components/media/SmartImage", () => ({
  default: ({ alt, className, srcRaw }: { alt?: string; className?: string; srcRaw?: string }) => (
    <img alt={alt} className={className} src={srcRaw} />
  ),
}))

const baseUser = {
  id: "u1",
  email: "u1@example.com",
  full_name: "User One",
  avatar_url: "/avatar.png",
  is_active: true,
  role: "student",
} as ComponentProps<typeof ProfileModal>["user"]

describe("ProfileModal contracts", () => {
  it("passes the documented i18n, media and focus-trap configuration", () => {
    const onClose = vi.fn()
    render(<ProfileModal user={baseUser} loading={false} error={null} onClose={onClose} />)

    expect(mocks.translation).toHaveBeenCalledWith(["messenger", "common"])
    expect(mocks.mediaQuery).toHaveBeenCalledWith("(prefers-reduced-motion: reduce)")
    expect(mocks.focusTrap).toHaveBeenCalledWith({
      active: true,
      onDeactivate: onClose,
      returnFocus: true,
    })
  })

  it("keeps dialog, overlay and close-button motion contracts when motion is allowed", () => {
    render(<ProfileModal user={baseUser} loading={false} error={null} onClose={() => {}} />)

    const overlay = mocks.motion.mock.calls.find(
      ([tag, props]) => tag === "div" && props.role === "presentation"
    )
    expect(overlay?.[1]).toMatchObject({
      initial: { opacity: 0 },
      animate: { opacity: 1 },
      exit: { opacity: 0 },
    })
    const dialog = mocks.motion.mock.calls.find(
      ([tag, props]) => tag === "div" && props.role === "dialog"
    )
    expect(dialog?.[1]).toMatchObject({
      initial: { opacity: 0, scale: 0.92, y: 20 },
      animate: { scale: 1, opacity: 1, y: 0 },
      exit: { scale: 0.92, opacity: 0, y: 20 },
    })
    const close = mocks.motion.mock.calls.find(([tag]) => tag === "button")
    expect(close?.[1]).toMatchObject({ whileHover: { scale: 1.08 }, whileTap: { scale: 0.92 } })
  })

  it("disables transform motion under reduced-motion preference", () => {
    mocks.mediaQuery.mockReturnValue(true)
    render(<ProfileModal user={baseUser} loading={false} error={null} onClose={() => {}} />)

    const dialog = mocks.motion.mock.calls.find(
      ([tag, props]) => tag === "div" && props.role === "dialog"
    )
    expect(dialog?.[1]).toMatchObject({
      initial: false,
      exit: { opacity: 0 },
      transition: { duration: 0 },
    })
    const close = mocks.motion.mock.calls.find(([tag]) => tag === "button")
    expect(close?.[1]).toMatchObject({ whileHover: undefined, whileTap: undefined })
    mocks.mediaQuery.mockReturnValue(false)
  })

  it("removes the Escape listener when the modal closes", () => {
    const add = vi.spyOn(document, "addEventListener")
    const remove = vi.spyOn(document, "removeEventListener")
    const onClose = vi.fn()
    const view = render(
      <ProfileModal user={baseUser} loading={false} error={null} onClose={onClose} />
    )
    const registration = add.mock.calls.find(([type]) => type === "keydown")
    expect(registration).toBeDefined()
    view.rerender(<ProfileModal user={null} loading={false} error={null} onClose={onClose} />)
    expect(remove).toHaveBeenCalledWith("keydown", registration![1])
    fireEvent.keyDown(document, { key: "Escape" })
    expect(onClose).not.toHaveBeenCalled()
    add.mockRestore()
    remove.mockRestore()
  })
})
