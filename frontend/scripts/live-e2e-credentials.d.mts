export function requireLiveAdminPassword(environment?: Record<string, string | undefined>): string

export function requireLiveStudentPassword(environment?: Record<string, string | undefined>): string

export function resolveLiveRolePassword(
  role: string,
  fallbackPassword: string,
  ownerInjected: boolean,
  environment?: Record<string, string | undefined>
): string
