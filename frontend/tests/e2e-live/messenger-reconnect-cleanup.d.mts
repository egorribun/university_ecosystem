export type MessengerReconnectContext = { close(): Promise<void> }

export type MessengerReconnectLocator = {
  count(): Promise<number>
  locator(selector: string): MessengerReconnectLocator
  getByRole(role: "button", options: { name: string; exact?: boolean }): MessengerReconnectLocator
  click(options: { timeout: number }): Promise<void>
}

export type MessengerReconnectLog<
  TLocator extends MessengerReconnectLocator = MessengerReconnectLocator,
> = {
  getByText(text: string, options: { exact: true }): TLocator
}

export type MessengerReconnectPage<
  TLocator extends MessengerReconnectLocator = MessengerReconnectLocator,
> = {
  getByRole(role: "alertdialog", options: { name: string }): TLocator
}

export function deleteOwnedMessengerMessage<TLocator extends MessengerReconnectLocator>(options: {
  page: MessengerReconnectPage<TLocator>
  log: MessengerReconnectLog<TLocator>
  content: string
  timeoutMs: number
  expectVisible(locator: TLocator, timeoutMs: number): Promise<void>
  expectCount(locator: TLocator, count: number, timeoutMs: number): Promise<void>
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
