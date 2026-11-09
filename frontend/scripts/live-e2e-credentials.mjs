export function requireLiveAdminPassword(environment = process.env) {
  const candidate = environment.TEST_PASSWORD
  if (typeof candidate !== "string" || candidate.trim().length === 0) {
    throw new Error("TEST_PASSWORD must be set for the live admin fixture")
  }
  return candidate
}

export function requireLiveStudentPassword(environment = process.env) {
  const candidate = environment.TEST_PASSWORD
  if (typeof candidate !== "string" || candidate.trim().length === 0) {
    throw new Error("TEST_PASSWORD must be set for the owned live student fixture")
  }
  return candidate
}

export function resolveLiveRolePassword(
  role,
  fallbackPassword,
  ownerInjected,
  environment = process.env
) {
  if (role === "student" && ownerInjected) {
    return requireLiveStudentPassword(environment)
  }
  return fallbackPassword
}
