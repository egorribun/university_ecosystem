const CASES = Object.freeze({
  "aud154-realtime": Object.freeze({
    file: "tests/e2e-live/messenger-realtime.live.spec.ts",
    title: "a message is delivered, edited, and tombstoned in the other authenticated session",
    grep: /a message is delivered, edited, and tombstoned in the other authenticated session/u,
    projects: Object.freeze(["desktop"]),
  }),
  "aud454-membership-revocation": Object.freeze({
    file: "tests/e2e-live/messenger-membership-revocation.live.spec.ts",
    title: "a removed member loses detail, history, reactor, attachment, send, and live access",
    grep: /a removed member loses detail, history, reactor, attachment, send, and live access/u,
    projects: Object.freeze(["desktop"]),
  }),
  "aud375-service-worker": Object.freeze({
    file: "tests/e2e/audit375-service-worker.spec.ts",
    title: "AUD-375 real service-worker replay",
    grep: /AUD-375 real service-worker replay/u,
    projects: Object.freeze(["desktop"]),
  }),
  "aud321-rate-limit-ux": Object.freeze({
    file: "tests/e2e/rate-limit-ux.spec.ts",
    title: "Rate limit UX",
    grep: /Rate limit UX/u,
    projects: Object.freeze(["desktop"]),
  }),
  "aud432-login-lockout": Object.freeze({
    file: "tests/e2e-live/auth-login-lockout.live.spec.ts",
    title: "synthetic account reaches account lockout after the configured failed-login threshold",
    grep: /synthetic account reaches account lockout after the configured failed-login threshold/u,
    projects: Object.freeze(["desktop", "mobile"]),
  }),
  "aud432-registration": Object.freeze({
    file: "tests/e2e-live/register-double-submit.live.spec.ts",
    title: "rapid double submit on a 360px registration form creates one account",
    grep: /rapid double submit on a 360px registration form creates one account/u,
    projects: Object.freeze(["desktop", "mobile"]),
  }),
  "aud501-hidden-clock": Object.freeze({
    file: "tests/e2e-live/story-viewer-keyboard.live.spec.ts",
    title: "a seeded story preserves elapsed playback across a clock-controlled hidden tab",
    grep: /a seeded story preserves elapsed playback across a clock-controlled hidden tab/u,
    projects: Object.freeze(["desktop", "mobile"]),
  }),
})

export function selectLiveAuditCases(requested, projectOverride) {
  if (!Array.isArray(requested) || requested.length === 0) {
    throw new TypeError("a non-empty closed case-ID list is required")
  }
  if (
    projectOverride !== undefined &&
    (typeof projectOverride !== "string" || !["desktop", "mobile"].includes(projectOverride))
  ) {
    throw new TypeError("invalid live audit project")
  }
  const seen = new Set()
  const selected = []
  for (const id of requested) {
    if (typeof id !== "string" || !Object.hasOwn(CASES, id) || seen.has(id)) {
      throw new TypeError("invalid live audit case selection")
    }
    if (projectOverride !== undefined && !CASES[id].projects.includes(projectOverride)) {
      throw new TypeError("live audit case is not mapped to the selected project")
    }
    seen.add(id)
    selected.push(CASES[id])
  }
  const files = [...new Set(selected.map(({ file }) => file))]
  const grep = Object.freeze(selected.map(({ grep: fixedGrep }) => fixedGrep))
  const projects =
    projectOverride === undefined
      ? [...new Set(selected.flatMap(({ projects: selectedProjects }) => selectedProjects))]
      : [projectOverride]
  return Object.freeze({
    files: Object.freeze(files),
    grep,
    projects: Object.freeze(projects),
  })
}

export function selectLiveAuditCasesFromEnvironment(raw, projectOverride) {
  if (raw === undefined) {
    if (projectOverride !== undefined) throw new TypeError("audit project requires case IDs")
    return undefined
  }
  if (typeof raw !== "string" || raw.length > 512) {
    throw new TypeError("invalid live audit case environment")
  }
  return selectLiveAuditCases(raw.split(","), projectOverride)
}

export const liveAuditCaseIds = Object.freeze(Object.keys(CASES))
