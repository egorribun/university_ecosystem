import { useState, useCallback, useRef, useEffect, useId } from "react"
import { useSearch, useNavigate } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { Settings as SettingsIcon } from "lucide-react"

import { PageLayout } from "@/components/layout/PageLayout"
import { Tabs, Tab, Snackbar, SettingsBackdrop } from "@/components/settings"
import { StepUpDialog } from "@/components/mfa/StepUpDialog"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"

import { SettingsGeneral } from "./settings/SettingsGeneral"
import { SettingsProfile } from "./settings/SettingsProfile"
import { SettingsSecurity } from "./settings/SettingsSecurity"
import { SettingsIntegrations } from "./settings/SettingsIntegrations"

export default function Settings() {
  const { t } = useTranslation(["settings", "common"])
  // Wave 134 SW2 — tab state lifted from useState into the URL query
  // string (?tab=N). Validated via settingsSearchSchema in
  // routes/_auth/settings.tsx; invalid values fall back to 0 (General).
  // Allows deep-linking from external sources (notification emails,
  // help docs) to a specific tab. Spotify-callback ?spotify= flag
  // (line ~50 below) was already URL-driven, this brings tab in line.
  //
  // strict: false — preserves the pre-W134 pattern so component-level
  // tests (Settings.media.test.tsx, Settings.radio.test.tsx, etc.) can
  // mount Settings without a fully-resolved /_auth/settings route
  // match. The schema-validated TanStack search is still surfaced as
  // a Record<string, unknown> here; we narrow the only fields we read
  // (tab + spotify) inline.
  const search = useSearch({ strict: false }) as { tab?: number; spotify?: string }
  const navigate = useNavigate()
  const tab = search.tab ?? 0
  // Wave 175 SW6 — stable panel id passed to Tabs + tabpanel wrapper so
  // each Tab gets aria-controls={panelId} and the tabpanel has matching
  // id + aria-labelledby={tabId of active tab} per ARIA APG.
  const panelBaseId = useId()
  const settingsPanelId = `${panelBaseId}-tabpanel`
  const activeTabId = `${settingsPanelId}-tab-${tab}`

  // Wave 184 SW6 (Path D) — viewport flags for SettingsBackdrop orb scaling
  // + GPU mitigation. Matches W181 SW2 MessengerBackdrop + W184 SW5
  // ProfileBackdrop convention. isNarrow at content breakpoint (~< 900px)
  // scales orbs down; isMobile (<= breakpoints.mobile) drops blur entirely.
  //
  // Within-iter SAME-mechanism sub-fix (W138 Lesson #1): originally used
  // framer-motion's useReducedMotion() — which caused vitest unhandled
  // errors in Settings.media.test.tsx + Settings.radio.test.tsx because
  // framer-motion's hook touches `window.matchMedia(...).addEventListener`
  // in initPrefersReducedMotion via a code path that jsdom's polyfill
  // doesn't fully cover. Switched to the project's own useMediaQuery hook
  // matching W184 SW5 Profile.tsx + W175 SW4 ProfileHeader convention —
  // useMediaQuery is jsdom-polyfilled in setupTests.ts (W113 SW6 baseline).
  const isNarrow = useMediaQuery(`(max-width: ${breakpoints.content})`)
  const isMobile = useMediaQuery(`(max-width: ${breakpoints.mobile})`)
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")

  // Shared Snackbar State
  const [snackbar, setSnackbar] = useState<{
    text: string
    severity?: "success" | "info" | "warning" | "error"
  } | null>(null)

  // StepUp State (Shared across tabs, mostly for Security)
  const [stepUpOpen, setStepUpOpen] = useState(false)
  const stepUpActionRef = useRef<(() => Promise<void>) | null>(null)

  const openStepUpFor = useCallback((action: () => Promise<void>) => {
    stepUpActionRef.current = action
    setStepUpOpen(true)
  }, [])

  const handleStepUpClose = useCallback(() => {
    setStepUpOpen(false)
    stepUpActionRef.current = null
  }, [])

  const handleStepUpCompleted = useCallback(async () => {
    const action = stepUpActionRef.current
    stepUpActionRef.current = null
    setStepUpOpen(false)
    if (action) {
      await action()
    }
  }, [])

  useEffect(() => {
    const spotifyStatus = search.spotify
    if (spotifyStatus) {
      if (spotifyStatus === "connected")
        setSnackbar({
          text: t("settings:integrations.spotify.snackbar.connected"),
          severity: "success",
        })
      if (spotifyStatus === "error")
        setSnackbar({
          text: t("settings:integrations.spotify.snackbar.connectFailed"),
          severity: "error",
        })

      // Clean up the URL param without refreshing
      void navigate({
        to: ".",
        search: (prev: Record<string, unknown>) => {
          const next = { ...prev }
          delete next.spotify
          return next
        },
        replace: true,
        viewTransition: false,
      })
    }
  }, [search, navigate, t])

  // Wave 134 SW2 — tab change navigates to /settings?tab=N. `replace: true`
  // so back button skips intermediate tabs (matches pre-W134 useState
  // behaviour where navigation history wasn't polluted). `viewTransition:
  // false` per FIX-77-03 — prevents view transition flash on tab change.
  const setTab = useCallback(
    (next: number) => {
      void navigate({
        to: ".",
        search: (prev: Record<string, unknown>) => {
          const out: Record<string, unknown> = { ...prev }
          // tab=0 is the default; omit from URL for a clean /-friendly state.
          if (next === 0) {
            delete out.tab
          } else {
            out.tab = next
          }
          return out
        },
        replace: true,
        viewTransition: false,
      })
    },
    [navigate]
  )

  return (
    <PageLayout variant="full">
      {/* Wave 184 SW6 (Path D) — settings-theme scope wrapper enables
          tokens/settings.css (slate/purple/slate-300 palette + matte cards
          + tab highlight) inside this subtree. SettingsBackdrop mounts
          inside the outer `relative` positioning context so its
          `absolute inset-0` orbs span the full Settings viewport (NOT
          per-tab — backdrop must NOT re-mount on tab change per FIX-77-03;
          conditional render here is route-level, gated by Settings.tsx
          rendering at all, which only happens at /settings route). */}
      <div className="settings-theme relative flex min-h-full w-full flex-col bg-(--bg-page) text-(--text-primary) sm:flex-row">
        <SettingsBackdrop
          isNarrow={isNarrow}
          isMobile={isMobile}
          prefersReducedMotion={prefersReducedMotion}
        />
        <div className="px-2 md:px-4 relative z-base">
          <div
            data-fade
            className="mb-8 flex flex-wrap items-center gap-4 sm:gap-5 animate-fade-in delay-(--motion-delay-short)"
          >
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-brand-subtle-bg text-brand shadow-premium transition-transform duration-fast hover:scale-105 backdrop-blur-sm">
              <SettingsIcon className="h-6 w-6" />
            </div>
            <h1
              className="font-bold tracking-tight text-(--text-primary)"
              style={{ fontSize: "var(--fs-page-title)" }}
            >
              {t("settings:page.title")}
            </h1>
          </div>

          <div data-fade className="mb-8 animate-fade-in delay-(--motion-delay-base)">
            <Tabs
              value={tab}
              onChange={(_, value) => setTab(value)}
              variant="scrollable"
              scrollButtons="auto"
              panelId={settingsPanelId}
              ariaLabel={t("settings:tabs.ariaLabel")}
              className="border-b border-(--border-subtle)"
            >
              <Tab label={t("settings:tabs.general")} />
              <Tab label={t("settings:tabs.account")} />
              <Tab label={t("settings:tabs.security")} />
              <Tab label={t("settings:tabs.integrations")} />
            </Tabs>
          </div>

          {/* Wave 175 SW6 — single stable tabpanel (W116 polish events tabs
              pattern). aria-labelledby points at the currently-active tab
              button id; aria-controls on every Tab points at this section. */}
          <section
            id={settingsPanelId}
            role="tabpanel"
            aria-labelledby={activeTabId}
            tabIndex={0}
            data-fade
            className="animate-fade-in delay-(--motion-delay-long) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-(--bg-page)"
          >
            {tab === 0 && <SettingsGeneral setSnackbar={setSnackbar} />}
            {tab === 1 && <SettingsProfile setSnackbar={setSnackbar} />}
            {tab === 2 && (
              <SettingsSecurity
                setSnackbar={setSnackbar}
                openStepUpFor={openStepUpFor}
                isActive={tab === 2}
              />
            )}
            {tab === 3 && <SettingsIntegrations setSnackbar={setSnackbar} />}
          </section>

          {/* StepUp Dialog */}
          <StepUpDialog
            open={stepUpOpen}
            onClose={handleStepUpClose}
            onCompleted={handleStepUpCompleted}
          />

          {/* Global Snackbar for Settings Page */}
          <Snackbar
            open={Boolean(snackbar)}
            onClose={() => setSnackbar(null)}
            autoHideDuration={6000}
            anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
          >
            {snackbar ? (
              <div
                className={`px-4 py-3 rounded-xl shadow-lg text-sm font-medium border ${
                  snackbar.severity === "error"
                    ? "bg-error-bg text-error-text border-error-text/(--opacity-dim)"
                    : snackbar.severity === "success"
                      ? "bg-success-bg text-success-text border-success-text/(--opacity-dim)"
                      : "bg-surface-raised text-text-primary border-border-subtle"
                }`}
              >
                {snackbar.text}
              </div>
            ) : null}
          </Snackbar>
        </div>
      </div>
    </PageLayout>
  )
}
