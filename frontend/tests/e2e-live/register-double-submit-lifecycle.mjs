import * as v from "valibot"

const RegistrationReceipt = v.strictObject({ status: v.literal("ok") })

export function isOpaqueRegistrationReceipt(value) {
  return v.safeParse(RegistrationReceipt, value).success
}

export async function waitForRegistrationCompletion(pending, timeoutMs) {
  if (pending.length === 0 || !Number.isFinite(timeoutMs) || timeoutMs < 1) return false
  let timer
  try {
    const expired = new Promise((resolve) => {
      timer = globalThis.setTimeout(() => resolve(false), timeoutMs)
    })
    const completed = Promise.all(pending).then(
      (results) => results.every((value) => value === true),
      () => false
    )
    return await Promise.race([completed, expired])
  } finally {
    globalThis.clearTimeout(timer)
  }
}

export async function withRegistrationDetach(action, detach, reportDetachFailure) {
  let actionFailed = false
  let result
  let actionError
  try {
    result = await action()
  } catch (error) {
    actionFailed = true
    actionError = error
  }
  try {
    await detach()
  } catch {
    if (!actionFailed) throw new Error("Registration browser cleanup failed")
    try {
      reportDetachFailure()
    } catch {
      // A diagnostic must not replace the original test failure.
    }
  }
  if (actionFailed) throw actionError
  return result
}
