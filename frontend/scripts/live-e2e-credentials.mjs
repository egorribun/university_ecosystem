export function requireLiveAdminPassword(environment = process.env) {
  const candidate = environment.TEST_PASSWORD
  if (typeof candidate !== "string" || candidate.trim().length === 0) {
    throw new Error("TEST_PASSWORD must be set for the live admin fixture")
  }
  return candidate
}
