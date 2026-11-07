// Ordering decisions for the live registration double-submit acceptance. The spec records
// each step into a trace; the contract test applies the same validator to synthetic traces.

/** The only legal order of the owned-registration steps, from navigation to page close. */
export const REGISTRATION_STEP_ORDER = Object.freeze([
  "navigated",
  "hydrated",
  "filled",
  "cleanup-registered",
  "listener-attached",
  "submitted",
  "receipt-verified",
  "logged-in",
  "identity-verified",
  "page-closed",
])

/**
 * Violations of the registration sequence for one trace and the observed registration POST
 * count. An empty array means every step ran once, in order, with exactly one POST.
 */
export function registrationTraceViolations(trace, postCount) {
  const violations = []
  const positions = new Map()
  trace.forEach((step, index) => {
    if (positions.has(step)) violations.push(`duplicate ${step}`)
    else positions.set(step, index)
  })
  for (const step of REGISTRATION_STEP_ORDER) {
    if (!positions.has(step)) violations.push(`missing ${step}`)
  }
  // Every pair must respect the total order, not only neighbouring steps.
  for (let earlierIndex = 0; earlierIndex < REGISTRATION_STEP_ORDER.length; earlierIndex += 1) {
    for (
      let laterIndex = earlierIndex + 1;
      laterIndex < REGISTRATION_STEP_ORDER.length;
      laterIndex += 1
    ) {
      const earlier = REGISTRATION_STEP_ORDER[earlierIndex]
      const later = REGISTRATION_STEP_ORDER[laterIndex]
      if (
        positions.has(earlier) &&
        positions.has(later) &&
        positions.get(earlier) > positions.get(later)
      ) {
        violations.push(`${later} before ${earlier}`)
      }
    }
  }
  if (postCount !== 1) violations.push(`expected exactly one registration POST, saw ${postCount}`)
  return violations
}
