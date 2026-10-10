export type PushContextOwner = {
  close: () => Promise<void>
}

export type PushBrowserOwner = {
  isConnected: () => boolean
}

export type PushOwnerCloseOptions = {
  context: PushContextOwner
  browser: PushBrowserOwner | undefined
  disconnected: Promise<void>
  disconnectObserved: () => boolean
  withTimeout: <T>(operation: Promise<T>, timeoutMs: number) => Promise<T>
  timeoutMs: number
}

export async function withVerifiedNativePushBrowserExit<T>(
  options: PushOwnerCloseOptions,
  afterVerifiedExit: () => Promise<T>
): Promise<T> {
  try {
    await options.withTimeout(options.context.close(), options.timeoutMs)
  } catch {
    // Closing can reject after the browser has already exited; only the exact
    // Browser disconnect observation below authorizes profile cleanup.
  }

  const browser = options.browser
  if (!browser) {
    throw new Error("Native Push browser identity is unavailable; profile preserved")
  }

  if (browser.isConnected() || !options.disconnectObserved()) {
    try {
      await options.withTimeout(options.disconnected, options.timeoutMs)
    } catch {
      // The fail-closed check below preserves the profile without exit proof.
    }
  }

  if (browser.isConnected() || !options.disconnectObserved()) {
    throw new Error("Native Push browser exit was not verified; profile preserved")
  }

  return afterVerifiedExit()
}

export function removeBeforeCleanupDeadline<T>(
  deadlineEpochMs: number,
  remove: () => T,
  now: () => number = Date.now
): T {
  if (now() >= deadlineEpochMs) {
    throw new Error("Native Push profile cleanup deadline expired; profile preserved")
  }
  return remove()
}
