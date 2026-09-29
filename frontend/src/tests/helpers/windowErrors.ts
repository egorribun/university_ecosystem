/**
 * React does not rethrow an exception raised by an event handler to the
 * caller of `fireEvent`: it reports it through the window `error` channel,
 * where Vitest would surface it as an unhandled error outside any test.
 * Collect those reports instead, so a test can assert that an interaction
 * completed without an uncaught exception.
 */
export function collectWindowErrors(action: () => void): unknown[] {
  const errors: unknown[] = []
  const onError = (event: ErrorEvent) => {
    event.preventDefault()
    errors.push(event.error)
  }
  window.addEventListener("error", onError)
  try {
    action()
  } finally {
    window.removeEventListener("error", onError)
  }
  return errors
}
