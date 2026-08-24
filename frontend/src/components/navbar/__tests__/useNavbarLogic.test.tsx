import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

type UserDouble = {
  role?: string
  full_name?: string | null
  avatar_url?: string | null
  avatar_updated_at?: number | null
  avatar_version?: number | null
  updated_at?: string | null
}

const mocks = vi.hoisted(() => ({
  pathname: "/",
  mobile: true,
  reducedMotion: false,
  user: null as UserDouble | null,
  navigate: vi.fn(),
  scrollToTop: vi.fn(),
  markScrollFromBottom: vi.fn(),
  isSamePath: vi.fn(),
  focusOptions: undefined as { active: boolean; onDeactivate?: () => void } | undefined,
  getNavigationConfig: vi.fn(() => [{ to: "/dashboard" }]),
  parseCacheVersion: vi.fn(() => "cache-v"),
}))

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => mocks.navigate,
  useRouterState: ({ select }: { select: (state: { location: { pathname: string } }) => string }) =>
    select({ location: { pathname: mocks.pathname } }),
}))
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { name?: string }) =>
      options?.name ? `${key}:${options.name}` : key,
  }),
}))
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: mocks.user, isAuth: Boolean(mocks.user), loading: false }),
}))
vi.mock("@/hooks/useMediaQuery", () => ({
  default: (query: string) => (query.includes("max-width") ? mocks.mobile : mocks.reducedMotion),
}))
vi.mock("@/hooks/useFocusTrap", () => ({
  default: (options: { active: boolean; onDeactivate?: () => void }) => {
    mocks.focusOptions = options
    return { current: null }
  },
}))
vi.mock("@/hooks/useScrollRestoration", () => ({
  default: () => ({
    scrollToTop: mocks.scrollToTop,
    markScrollFromBottom: mocks.markScrollFromBottom,
    isSamePath: mocks.isSamePath,
  }),
}))
vi.mock("@/hooks/ui/useScrollBehavior", () => ({
  useScrollBehavior: () => ({ isScrolled: true }),
}))
vi.mock("@/config/navigation", () => ({ getNavigationConfig: mocks.getNavigationConfig }))
vi.mock("@/utils/cache", () => ({ parseCacheVersion: mocks.parseCacheVersion }))

import { useNavbarLogic } from "@/components/navbar/useNavbarLogic"

describe("useNavbarLogic", () => {
  beforeEach(() => {
    mocks.pathname = "/"
    mocks.mobile = true
    mocks.reducedMotion = false
    mocks.user = null
    mocks.navigate.mockReset()
    mocks.scrollToTop.mockReset()
    mocks.markScrollFromBottom.mockReset()
    mocks.isSamePath.mockReset().mockReturnValue(false)
    mocks.getNavigationConfig.mockClear()
    mocks.parseCacheVersion.mockClear()
    mocks.focusOptions = undefined
  })

  it("derives anonymous and authenticated presentation state", async () => {
    const { result, rerender } = renderHook(() => useNavbarLogic())
    await waitFor(() => expect(result.current.isMobile).toBe(true))

    expect(result.current.profileAlt).toBe("navigation:aria.profileAvatar")
    expect(result.current.avatarSource).toBe("")
    expect(result.current.hasAvatar).toBe(false)
    expect(result.current.isAuth).toBe(false)

    mocks.user = {
      role: "student",
      full_name: "Ada",
      avatar_url: "https://cdn.test/ada.webp",
      avatar_updated_at: 7,
    }
    rerender()

    expect(result.current.profileAlt).toBe("navigation:aria.profileAvatarNamed:Ada")
    expect(result.current.avatarSource).toBe("https://cdn.test/ada.webp")
    expect(result.current.hasAvatar).toBe(true)
    expect(result.current.avatarCacheV).toBe("cache-v")
    expect(mocks.parseCacheVersion).toHaveBeenLastCalledWith(7)
    expect(mocks.getNavigationConfig).toHaveBeenLastCalledWith(expect.any(Function), "student")

    mocks.user = { ...mocks.user, avatar_updated_at: null, avatar_version: 8 }
    rerender()
    expect(mocks.parseCacheVersion).toHaveBeenLastCalledWith(8)

    mocks.user = {
      ...mocks.user,
      avatar_version: null,
      updated_at: "2026-08-14T00:00:00Z",
    }
    rerender()
    expect(mocks.parseCacheVersion).toHaveBeenLastCalledWith("2026-08-14T00:00:00Z")
  })

  it("recognizes dashboard descendants and exact non-dashboard routes", async () => {
    const { result, rerender } = renderHook(() => useNavbarLogic())
    await waitFor(() => expect(result.current.isMobile).toBe(true))

    expect(result.current.isActive("/dashboard")).toBe(true)
    expect(result.current.isActive("/news")).toBe(false)

    mocks.pathname = "/dashboard"
    rerender()
    expect(result.current.isActive("/dashboard")).toBe(true)

    mocks.pathname = "/dashboard/activity"
    rerender()
    expect(result.current.isActive("/dashboard")).toBe(true)

    mocks.pathname = "/dashboardish"
    rerender()
    expect(result.current.isActive("/dashboard")).toBe(false)

    mocks.pathname = "/news"
    rerender()
    expect(result.current.isActive("/news")).toBe(true)
  })

  it("scrolls same-route navigation and navigates to a different route", async () => {
    const { result, rerender } = renderHook(() => useNavbarLogic())
    await waitFor(() => expect(result.current.isMobile).toBe(true))

    mocks.isSamePath.mockImplementation((to: string) => to === "/same")
    act(() => result.current.go("/same"))
    expect(mocks.scrollToTop).toHaveBeenCalledWith("smooth")

    mocks.reducedMotion = true
    rerender()
    act(() => result.current.go("/same"))
    expect(mocks.scrollToTop).toHaveBeenLastCalledWith("auto")

    act(() => result.current.go("/news"))
    expect(mocks.markScrollFromBottom).toHaveBeenCalledOnce()
    expect(mocks.navigate).toHaveBeenCalledWith({ to: "/news" })
  })

  it("closes the mobile menu on deactivation, desktop transition, and route change", async () => {
    const { result, rerender } = renderHook(() => useNavbarLogic())
    await waitFor(() => expect(result.current.isMobile).toBe(true))

    act(() => result.current.setMobileMenu(true))
    expect(result.current.mobileMenu).toBe(true)
    expect(mocks.focusOptions?.active).toBe(true)
    act(() => mocks.focusOptions?.onDeactivate?.())
    expect(result.current.mobileMenu).toBe(false)

    act(() => result.current.setMobileMenu(true))
    mocks.mobile = false
    rerender()
    await waitFor(() => expect(result.current.mobileMenu).toBe(false))

    mocks.mobile = true
    rerender()
    await waitFor(() => expect(result.current.isMobile).toBe(true))
    act(() => result.current.setMobileMenu(true))
    mocks.pathname = "/events"
    rerender()
    await waitFor(() => expect(result.current.mobileMenu).toBe(false))
  })
})
