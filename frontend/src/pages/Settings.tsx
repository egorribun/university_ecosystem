import { useState, useCallback, useRef, useEffect } from "react"
import { useSearchParams } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Settings as SettingsIcon } from "lucide-react"

import { PageLayout } from "@/components/PageLayout"
import { Tabs, Tab, Snackbar } from "../components/settings"
import { StepUpDialog } from "../components/mfa/StepUpDialog"

import { SettingsGeneral } from "./settings/SettingsGeneral"
import { SettingsProfile } from "./settings/SettingsProfile"
import { SettingsSecurity } from "./settings/SettingsSecurity"
import { SettingsIntegrations } from "./settings/SettingsIntegrations"

export default function Settings() {
  const { t } = useTranslation(["settings", "common"])
  const [searchParams, setSearchParams] = useSearchParams()
  const [tab, setTab] = useState(0)

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
    const spotifyStatus = searchParams.get("spotify")
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
      setSearchParams((prev) => {
        const newParams = new URLSearchParams(prev)
        newParams.delete("spotify")
        return newParams
      })
    }
  }, [searchParams, setSearchParams, t])

  return (
    <PageLayout variant="full">
      <div className="flex h-full w-full flex-col bg-(--bg-page) text-(--text-primary) sm:h-160 sm:max-h-[85vh] sm:flex-row">
        <div className="px-2 md:px-4">
          <div
            data-fade
            className="mb-8 flex flex-wrap items-center gap-4 sm:gap-5 animate-fade-in delay-100"
          >
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-brand-subtle-bg text-brand shadow-premium transition-transform duration-200 hover:scale-105 backdrop-blur-sm">
              <SettingsIcon className="h-6 w-6" />
            </div>
            <h1 className="text-(length:--fs-page-title) font-bold tracking-tight text-(--text-primary)">
              {t("settings:page.title")}
            </h1>
          </div>

          <div data-fade className="mb-8 animate-fade-in delay-150">
            <Tabs
              value={tab}
              onChange={(_, value) => setTab(value)}
              variant="scrollable"
              scrollButtons="auto"
              className="border-b border-(--border-subtle)"
            >
              <Tab label={t("settings:tabs.general")} />
              <Tab label={t("settings:tabs.account")} />
              <Tab label={t("settings:tabs.security")} />
              <Tab label={t("settings:tabs.integrations")} />
            </Tabs>
          </div>

          <div data-fade className="animate-fade-in delay-200">
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
          </div>

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
                className={`px-4 py-3 rounded-lg shadow-lg text-sm font-medium border ${
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
