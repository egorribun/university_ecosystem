const PROFILE_USER_API_ROOT = "/api/v1/users"
const PROFILE_WRITE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"])

export function isProfileMutationRequest(method, pathname) {
  return (
    PROFILE_WRITE_METHODS.has(method) &&
    (pathname === PROFILE_USER_API_ROOT || pathname.startsWith(PROFILE_USER_API_ROOT + "/"))
  )
}
