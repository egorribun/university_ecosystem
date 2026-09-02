import { AppearanceSection } from "./sections"

import type { SetSnackbar } from "./types"

interface SettingsGeneralProps {
  setSnackbar: SetSnackbar
}

export function SettingsGeneral({ setSnackbar }: SettingsGeneralProps) {
  return (
    <div className="flex w-full flex-col gap-8 sm:gap-10 xl:max-w-(--layout-max-page) 2xl:gap-12 animate-fade-in delay-200">
      <AppearanceSection setSnackbar={setSnackbar} />
    </div>
  )
}
