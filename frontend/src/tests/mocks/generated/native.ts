import { setupServer } from 'msw/node'
import { handlers } from './handlers'
type NativeServer = Pick<ReturnType<typeof setupServer>, 'listen' | 'close' | 'use' | 'restoreHandlers' | 'resetHandlers' | 'listHandlers' | 'events'>
export const server: NativeServer = setupServer(...handlers)