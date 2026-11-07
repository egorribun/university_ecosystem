// Decisions the live lockout acceptance applies to real responses. The spec and its
// behaviour-level contract import the same functions, so neither can drift apart.

/** Backend default `AUTH_LOCKOUT_THRESHOLDS` (attempts:seconds, comma-separated). */
export const DEFAULT_AUTH_LOCKOUT_THRESHOLDS = "5:30,8:300,10:3600"

/**
 * Parses the backend lockout rule list. Attempt counts and cooldowns must be positive
 * integers, and both must strictly increase so the first rule is the earliest lockout.
 */
export function parseLockoutThresholds(value) {
  if (typeof value !== "string" || value.trim() === "") {
    throw new TypeError("lockout thresholds must be a non-empty string")
  }
  const rules = value.split(",").map((entry) => {
    const match = /^(\d+):(\d+)$/u.exec(entry.trim())
    if (!match) throw new TypeError(`malformed lockout rule: ${entry}`)
    const attempts = Number(match[1])
    const seconds = Number(match[2])
    if (attempts < 1 || seconds < 1) throw new TypeError(`non-positive lockout rule: ${entry}`)
    return { attempts, seconds }
  })
  for (let index = 1; index < rules.length; index += 1) {
    const previous = rules[index - 1]
    const current = rules[index]
    if (current.attempts <= previous.attempts || current.seconds <= previous.seconds) {
      throw new TypeError("lockout rules must strictly increase in attempts and cooldown")
    }
  }
  return rules
}

/** The earliest lockout rule, which the live scenario exercises. */
export function firstLockoutRule(value = DEFAULT_AUTH_LOCKOUT_THRESHOLDS) {
  return parseLockoutThresholds(value)[0]
}

/** Expected HTTP status for the nth consecutive wrong-password attempt (1-based). */
export function expectedFailedAttemptStatus(attempt, rule) {
  if (!Number.isInteger(attempt) || attempt < 1) throw new RangeError("attempt must be 1 or more")
  return attempt < rule.attempts ? 401 : 423
}

/** HTTP 423 is the account-lockout response. */
export function isAccountLockedStatus(status) {
  return status === 423
}

/**
 * A lockout Retry-After must be a plain positive integer no longer than the first cooldown.
 * Missing headers, fractions, signs and non-numeric text are rejected.
 */
export function lockoutRetryAfterWithinRule(headerValue, rule) {
  if (typeof headerValue !== "string" || !/^\d+$/u.test(headerValue)) return false
  const seconds = Number(headerValue)
  return seconds > 0 && seconds <= rule.seconds
}
