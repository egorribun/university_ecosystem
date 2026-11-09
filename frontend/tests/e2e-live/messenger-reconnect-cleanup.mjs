import { clearTimeout, setTimeout } from "node:timers"

const DEFAULT_CLEANUP_TIMEOUT_MS = 15_000

function withTimeout(operation, timeoutMs) {
  let timer
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(
      () => reject(new Error("Messenger reconnect cleanup operation timed out")),
      Math.max(1, timeoutMs)
    )
  })

  return Promise.race([operation, timeout]).finally(() => clearTimeout(timer))
}

function cleanupFailureMessage(failedMessageDeletions, failedContextCloses, timeoutMs) {
  const failures = []
  if (failedMessageDeletions > 0) {
    const count =
      failedMessageDeletions === 1
        ? "1 sender-owned message"
        : `${failedMessageDeletions} sender-owned messages`
    failures.push(`${count} could not be deleted`)
  }
  if (failedContextCloses > 0) {
    const count =
      failedContextCloses === 1
        ? "1 isolated browser context"
        : `${failedContextCloses} isolated browser contexts`
    failures.push(`${count} could not be closed`)
  }
  return `Messenger reconnect cleanup failed within ${timeoutMs} ms: ${failures.join("; ")}.`
}

export async function deleteOwnedMessengerMessage({
  page,
  log,
  content,
  timeoutMs,
  expectVisible,
  expectCount,
}) {
  const deadline = Date.now() + timeoutMs
  const remainingTimeout = () => {
    const remainingMs = deadline - Date.now()
    if (remainingMs <= 0) throw new Error("Owned message cleanup deadline expired")
    return remainingMs
  }

  const message = log.getByText(content, { exact: true })
  // The message is already absent, so there is nothing left for cleanup to delete.
  if ((await message.count()) === 0) return

  const row = message.locator(
    "xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' group ')][1]"
  )
  const deleteButton = row.getByRole("button", {
    name: "Удалить сообщение",
    exact: true,
  })
  if ((await deleteButton.count()) === 0) {
    throw new Error("Owned message cleanup could not find the delete control.")
  }

  await deleteButton.click({ timeout: remainingTimeout() })
  const dialog = page.getByRole("alertdialog", { name: "Удалить сообщение" })
  await expectVisible(dialog, remainingTimeout())
  await dialog.getByRole("button", { name: "Удалить", exact: true }).click({
    timeout: remainingTimeout(),
  })
  await expectCount(message, 0, remainingTimeout())
}

export async function cleanupMessengerReconnect({
  hasOwnerLog,
  createdMessages,
  deleteMessage,
  contexts,
  timeoutMs = DEFAULT_CLEANUP_TIMEOUT_MS,
}) {
  const cleanupTimeoutMs = timeoutMs
  const deadline = Date.now() + cleanupTimeoutMs
  let failedMessageDeletions = 0

  if (hasOwnerLog) {
    for (let index = 0; index < createdMessages.length; index += 1) {
      const remainingMs = deadline - Date.now()
      if (remainingMs <= 0) {
        failedMessageDeletions += createdMessages.length - index
        break
      }

      const remainingMessages = createdMessages.length - index
      const operationTimeoutMs = Math.max(1, Math.floor(remainingMs / remainingMessages))
      try {
        await withTimeout(
          Promise.resolve().then(() => deleteMessage(createdMessages[index], operationTimeoutMs)),
          operationTimeoutMs
        )
      } catch {
        failedMessageDeletions += 1
      }
    }
  }

  const contextCloseResults = await Promise.all(
    contexts.map(async (context) => {
      const remainingMs = Math.max(1, deadline - Date.now())
      try {
        await withTimeout(
          Promise.resolve().then(() => context.close()),
          remainingMs
        )
        return true
      } catch {
        return false
      }
    })
  )
  const failedContextCloses = contextCloseResults.filter((closed) => !closed).length

  if (failedMessageDeletions === 0 && failedContextCloses === 0) return null
  return cleanupFailureMessage(failedMessageDeletions, failedContextCloses, cleanupTimeoutMs)
}

export async function withMessengerReconnectCleanup({ run, cleanup, onCleanupFailure }) {
  let primaryFailure
  let primaryFailed = false
  try {
    await run()
  } catch (error) {
    primaryFailed = true
    primaryFailure = error
  }

  let cleanupFailure
  try {
    cleanupFailure = await cleanup()
  } catch {
    cleanupFailure = "Messenger reconnect cleanup could not complete."
  }

  if (cleanupFailure) {
    try {
      onCleanupFailure?.(cleanupFailure)
    } catch {
      // Reporting cleanup must not replace a test failure or cleanup failure.
    }
    if (!primaryFailed) throw new Error(cleanupFailure)
  }

  if (primaryFailed) throw primaryFailure
}
