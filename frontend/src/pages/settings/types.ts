export type SnackbarState = {
  text: string
  severity?: "success" | "info" | "warning" | "error"
} | null

export type SetSnackbar = (value: SnackbarState) => void

export interface SettingsSectionProps {
  setSnackbar: SetSnackbar
}




