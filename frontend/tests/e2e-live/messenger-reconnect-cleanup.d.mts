export type MessengerReconnectContext = { close(): Promise<void> }

export type MessengerReconnectLocator = {
  count(): Promise<number>
  locator(selector: string): MessengerReconnectLocator
  getByRole(role: "button", options: { name: string; exact?: boolean }): MessengerReconnectLocator
  click(options: { timeout: number }): Promise<void>
}

export type MessengerReconnectLog = {
  getByText(text: string, options: { exact: true }): MessengerReconnectLocator
}

export type MessengerReconnectPage = {
  getByRole(role: "alertdialog", options: { name: string }): MessengerReconnectLocator
}

export function deleteOwnedMessengerMessage(options: {
  page: MessengerReconnectPage
  log: MessengerReconnectLog
  content: string
  timeoutMs: number
  expectVisible(locator: MessengerReconnectLocator, timeoutMs: number): Promise<void>
  expectCount(locator: MessengerReconnectLocator, count: number, timeoutMs: number): Promise<void>
}): Promise<void>

export function cleanupMessengerReconnect(options: {
  hasOwnerLog: boolean
  createdMessages: readonly string[]
  deleteMessage: (content: string, timeoutMs: number) => Promise<void>
  contexts: readonly MessengerReconnectContext[]
  timeoutMs?: number
}): Promise<string | null>

export function withMessengerReconnectCleanup(options: {
  run(): Promise<void>
  cleanup(): Promise<string | null>
  onCleanupFailure?(description: string): void
}): Promise<void>
