type UploadIdleState = { status: "idle" }
type UploadSuccessState = { status: "success" }
export type UploadErrorState = { status: "error"; error: string }

export type UploadState = UploadIdleState | UploadSuccessState | UploadErrorState

export const isUploadErrorState = (state: UploadState): state is UploadErrorState =>
  state.status === "error"

export type OptimisticEventFile = {
  id: string
  event_id: string
  description?: string | null
  file_url: string
  pending?: boolean
}

export type FileOptimisticAction =
  { type: "add"; file: OptimisticEventFile } | { type: "remove"; id: OptimisticEventFile["id"] }

export const applyOptimisticFileAction = (
  current: OptimisticEventFile[],
  action: FileOptimisticAction
): OptimisticEventFile[] => {
  switch (action.type) {
    case "add":
      return [...current, action.file]
    case "remove":
      return current.filter((file) => file.id !== action.id)
    default:
      return current
  }
}
