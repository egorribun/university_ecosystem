/**
 * App Shell Store
 *
 * Manages application chrome state: sidebar, drawer, theme.
 * Persists theme preference to localStorage.
 */

import { create } from "zustand"
import { devtools, persist } from "zustand/middleware"

import type { ThemeMode } from "./types"

interface AppShellState {
  /** Whether sidebar is collapsed (desktop) */
  sidebarCollapsed: boolean

  /** Whether mobile drawer is open */
  mobileDrawerOpen: boolean

  /** Theme mode preference */
  themeMode: ThemeMode

  /** Toggle sidebar collapsed state */
  toggleSidebar: () => void

  /** Set sidebar collapsed state */
  setSidebarCollapsed: (collapsed: boolean) => void

  /** Open mobile drawer */
  openMobileDrawer: () => void

  /** Close mobile drawer */
  closeMobileDrawer: () => void

  /** Toggle mobile drawer */
  toggleMobileDrawer: () => void

  /** Set theme mode */
  setThemeMode: (mode: ThemeMode) => void

  /** Cycle through theme modes */
  cycleThemeMode: () => void
}

const THEME_CYCLE: ThemeMode[] = ["system", "light", "dark"]

export const useAppShellStore = create<AppShellState>()(
  devtools(
    persist(
      (set) => ({
        sidebarCollapsed: false,
        mobileDrawerOpen: false,
        themeMode: "system",

        toggleSidebar: () =>
          set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed }), false, "toggleSidebar"),

        setSidebarCollapsed: (collapsed) =>
          set({ sidebarCollapsed: collapsed }, false, "setSidebarCollapsed"),

        openMobileDrawer: () => set({ mobileDrawerOpen: true }, false, "openMobileDrawer"),

        closeMobileDrawer: () => set({ mobileDrawerOpen: false }, false, "closeMobileDrawer"),

        toggleMobileDrawer: () =>
          set(
            (state) => ({ mobileDrawerOpen: !state.mobileDrawerOpen }),
            false,
            "toggleMobileDrawer"
          ),

        setThemeMode: (mode) => set({ themeMode: mode }, false, "setThemeMode"),

        cycleThemeMode: () =>
          set(
            (state) => {
              const currentIndex = THEME_CYCLE.indexOf(state.themeMode)
              const nextIndex = (currentIndex + 1) % THEME_CYCLE.length
              return { themeMode: THEME_CYCLE[nextIndex] }
            },
            false,
            "cycleThemeMode"
          ),
      }),
      {
        name: "app-shell-preferences",
        partialize: (state) => ({
          sidebarCollapsed: state.sidebarCollapsed,
          themeMode: state.themeMode,
        }),
      }
    ),
    { name: "AppShellStore" }
  )
)

/** Selector hooks for optimized re-renders */
export const useSidebarCollapsed = () => useAppShellStore((state) => state.sidebarCollapsed)

export const useMobileDrawerOpen = () => useAppShellStore((state) => state.mobileDrawerOpen)

export const useThemeMode = () => useAppShellStore((state) => state.themeMode)

export const useAppShellActions = () =>
  useAppShellStore((state) => ({
    toggleSidebar: state.toggleSidebar,
    setSidebarCollapsed: state.setSidebarCollapsed,
    openMobileDrawer: state.openMobileDrawer,
    closeMobileDrawer: state.closeMobileDrawer,
    toggleMobileDrawer: state.toggleMobileDrawer,
    setThemeMode: state.setThemeMode,
    cycleThemeMode: state.cycleThemeMode,
  }))
