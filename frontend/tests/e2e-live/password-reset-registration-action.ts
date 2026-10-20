export type ResetRegistrationStep = "arm-response" | "click" | "await-response"

export async function runPasswordResetRegistrationAction<T>(
  armResponse: () => Promise<T>,
  click: () => Promise<unknown>,
  reportFailure: (step: ResetRegistrationStep) => void
): Promise<T> {
  let step: ResetRegistrationStep = "arm-response"
  try {
    const pending = armResponse()
    // Own a later rejection even when clicking fails before the original await.
    // Awaiting the original promise below still propagates response failures.
    void pending.catch(() => undefined)
    step = "click"
    await click()
    step = "await-response"
    return await pending
  } catch (error) {
    try {
      reportFailure(step)
    } catch {
      // A diagnostic sink must never replace the original operation error.
    }
    throw error
  }
}
