import type { ReactNode } from "react"
import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"

import { LanguageProvider, useLanguage } from "@/contexts/LanguageContext"
import { createI18nInstance } from "@/i18n/config"
import StoriesAdmin from "../StoriesAdmin"

const mocks = vi.hoisted(() => ({
  getStories: vi.fn(),
  now: new Date("2026-01-01T12:00:00.000Z"),
}))

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: { id: "admin", role: "admin" } }),
}))
vi.mock("@/api/client", () => ({ default: { get: mocks.getStories } }))
vi.mock("@/api/stories", () => ({
  StoryCoverUploadError: class extends Error {},
  createStory: vi.fn(),
  deleteStory: vi.fn(),
  updateStory: vi.fn(),
  uploadStoryCover: vi.fn(),
}))
vi.mock("@/hooks/useScheduleClock", () => ({ useScheduleClock: () => mocks.now }))
vi.mock("@/components/Layout", () => ({
  default: ({ children }: { children: ReactNode }) => <>{children}</>,
}))
vi.mock("@/components/motion/PageFadeIn", () => ({
  default: ({ children }: { children: ReactNode }) => <>{children}</>,
}))
vi.mock("@/components/media/SmartImage", () => ({ default: () => null }))
vi.mock("@/components/settings", () => ({
  Alert: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  Button: ({ children }: { children?: ReactNode }) => <button type="button">{children}</button>,
  CircularProgress: () => null,
  Divider: () => null,
  SectionCard: ({ children }: { children: ReactNode }) => <section>{children}</section>,
  TextField: () => null,
}))
vi.mock("@/components/ui/Badge", () => ({
  Badge: ({ children }: { children: ReactNode }) => <span>{children}</span>,
}))
vi.mock("@/components/ui/Card", () => ({
  Card: ({ children }: { children: ReactNode }) => <article>{children}</article>,
}))
vi.mock("@/components/ui/ConfirmDialog", () => ({ ConfirmDialog: () => null }))

function LanguageControls() {
  const { setLanguage } = useLanguage()
  return (
    <div>
      <button type="button" onClick={() => setLanguage("en")}>
        English
      </button>
      <button type="button" onClick={() => setLanguage("ru")}>
        Русский
      </button>
    </div>
  )
}

function restoreAttribute(element: Element, name: string, value: string | null) {
  if (value === null) element.removeAttribute(name)
  else element.setAttribute(name, value)
}

beforeEach(() => {
  mocks.now = new Date("2026-01-01T12:00:00.000Z")
  mocks.getStories.mockReset()
  mocks.getStories.mockResolvedValue({
    data: [
      {
        id: "story-locale",
        title: "Locale story",
        short_text: "Story text",
        published_at: "2026-01-01T11:30:00.000Z",
        expires_at: "2026-01-01T12:02:00.000Z",
        is_active: true,
        created_at: "2026-01-01T11:00:00.000Z",
      },
    ],
  })
})

it("updates story expiry text across language changes and clock boundaries", async () => {
  const previousSelected = window.__UE_SELECTED_LANG__
  const previousGetter = globalThis.__ssrI18nGetter__
  const previousStorage = localStorage.getItem("ue:language")
  const htmlLanguage = document.documentElement.getAttribute("lang")
  const htmlDirection = document.documentElement.getAttribute("dir")
  const bodyDirection = document.body.getAttribute("dir")
  const instance = createI18nInstance("en")
  const cookieSetter = vi.spyOn(document, "cookie", "set").mockImplementation(() => {})
  const tree = () => (
    <LanguageProvider>
      <LanguageControls />
      <StoriesAdmin />
    </LanguageProvider>
  )
  let view: ReturnType<typeof render> | undefined

  try {
    window.__UE_SELECTED_LANG__ = "en"
    globalThis.__ssrI18nGetter__ = () => instance
    view = render(tree())
    await screen.findByText("Locale story")
    const badge = screen.getByText("in 2 minutes")

    fireEvent.click(screen.getByRole("button", { name: "Русский" }))
    expect(await screen.findByText("через 2 минуты")).toBe(badge)

    mocks.now = new Date("2026-01-01T12:01:00.000Z")
    view.rerender(tree())
    expect(screen.getByText("через 1 минуту")).toBe(badge)

    mocks.now = new Date("2026-01-01T12:03:00.000Z")
    view.rerender(tree())
    expect(screen.getByText("1 минуту назад")).toBe(badge)

    fireEvent.click(screen.getByRole("button", { name: "English" }))
    expect(await screen.findByText("1 minute ago")).toBe(badge)
  } finally {
    view?.unmount()
    if (previousSelected === undefined) delete window.__UE_SELECTED_LANG__
    else window.__UE_SELECTED_LANG__ = previousSelected
    globalThis.__ssrI18nGetter__ = previousGetter
    if (previousStorage === null) localStorage.removeItem("ue:language")
    else localStorage.setItem("ue:language", previousStorage)
    cookieSetter.mockRestore()
    restoreAttribute(document.documentElement, "lang", htmlLanguage)
    restoreAttribute(document.documentElement, "dir", htmlDirection)
    restoreAttribute(document.body, "dir", bodyDirection)
  }
})
