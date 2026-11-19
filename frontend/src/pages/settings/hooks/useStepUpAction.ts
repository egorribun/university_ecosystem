import { useCallback, useEffect, useRef, useState } from "react"
import { useAuth } from "@/contexts/AuthContext"
import { useConfirmedIdentityPending } from "@/hooks/useConfirmedIdentityPending"
import { useProfileSessionGuard } from "@/hooks/useProfileSessionGuard"
import { getConfirmedUserId } from "@/stores/authIdentity"

type StepUpAttempt = {
  id: number
  userId: string
  isCurrent: () => boolean
  action: () => Promise<void>
}

/** Keep a verified settings action tied to its dialog and initiating session. */
export function useStepUpAction() {
  const { user, loading } = useAuth()
  const captureOperation = useProfileSessionGuard()
  const identityPending = useConfirmedIdentityPending()
  const confirmedUserId = getConfirmedUserId({ user, loading })
  const userId = user?.id == null ? null : String(user.id).trim()
  const nextId = useRef(0)
  const dialog = useRef<StepUpAttempt | null>(null)
  const pending = useRef<StepUpAttempt | null>(null)
  const [dialogId, setDialogId] = useState<number | null>(null)
  const [replayId, setReplayId] = useState<number | null>(null)

  const openStepUpFor = useCallback(
    (action: () => Promise<void>) => {
      const isCurrent = captureOperation()
      if (!confirmedUserId || !isCurrent()) return
      const attempt = { id: ++nextId.current, userId: confirmedUserId, isCurrent, action }
      pending.current = null
      dialog.current = attempt
      setReplayId(null)
      setDialogId(attempt.id)
    },
    [captureOperation, confirmedUserId]
  )

  const closeStepUp = useCallback((id: number) => {
    if (dialog.current?.id !== id) return
    dialog.current = null
    setDialogId(null)
  }, [])

  const completeStepUp = useCallback((id: number) => {
    const attempt = dialog.current
    if (!attempt || attempt.id !== id) return
    dialog.current = null
    setDialogId(null)
    pending.current = attempt
    setReplayId(id)
  }, [])

  useEffect(() => {
    const activeDialog = dialog.current
    if (activeDialog && (!activeDialog.isCurrent() || userId !== activeDialog.userId)) {
      dialog.current = null
      setDialogId(null)
    }
    const attempt = pending.current
    if (!attempt || attempt.id !== replayId) return
    if (!attempt.isCurrent() || userId !== attempt.userId) {
      pending.current = null
      setReplayId(null)
      return
    }
    if (identityPending) return
    // Claim the action before invoking it so StrictMode cannot replay it twice.
    pending.current = null
    setReplayId(null)
    void attempt.action()
  }, [captureOperation, identityPending, replayId, userId])

  useEffect(
    () => () => {
      dialog.current = null
      pending.current = null
    },
    []
  )

  return { dialogId, openStepUpFor, closeStepUp, completeStepUp }
}
