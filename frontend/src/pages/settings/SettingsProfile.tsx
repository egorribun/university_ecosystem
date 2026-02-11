import React from "react"
import { ProfileSection } from "./sections"
import type { SetSnackbar } from "./types"

interface SettingsProfileProps {
  setSnackbar: SetSnackbar
}

export function SettingsProfile({ setSnackbar }: SettingsProfileProps) {
  return (
    <div className="flex w-full flex-col gap-5 sm:gap-6 xl:max-w-(--layout-max-page) 2xl:max-w-(--layout-max-wide) animate-fade-in delay-200">
      <ProfileSection setSnackbar={setSnackbar} />
    </div>
  )
}
