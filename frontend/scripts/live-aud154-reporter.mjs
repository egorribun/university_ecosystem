import { resolve } from "node:path"
import process from "node:process"
import { fileURLToPath } from "node:url"

const CASE_IDS = new Map([
  [
    "a message is delivered, edited, and tombstoned in the other authenticated session",
    "aud154-sent-confirmation",
  ],
  [
    "shows sent confirmation after the server accepts the message",
    "aud154-enter-sent-confirmation",
  ],
])
const CASE_FILE = fileURLToPath(
  new URL("../tests/e2e-live/messenger-realtime.live.spec.ts", import.meta.url)
)
const STATUSES = new Set(["passed", "failed", "timedOut", "skipped", "interrupted"])
const OUTCOMES = new Set(["expected", "unexpected", "flaky", "skipped"])

// Read final Playwright results, not a success marker emitted inside the test.
// Never serialize titles, errors, attachments, stdout, URLs, or fixture values.
export default class Aud154Reporter {
  constructor(_options = {}, write = (line) => process.stdout.write(line)) {
    this.write = write
    this.tests = []
  }

  onBegin(_config, suite) {
    this.tests = suite
      .allTests()
      .filter(
        (item) =>
          resolve(item.location.file) === CASE_FILE &&
          CASE_IDS.has(item.title) &&
          item.parent.title === "live messenger delivery" &&
          ["desktop", "mobile"].includes(item.parent.project()?.name)
      )
  }

  onEnd() {
    const records = []
    const identities = new Set()
    for (const item of this.tests) {
      const project = item.parent.project().name
      const caseId = CASE_IDS.get(item.title)
      const identity = `${caseId}:${project}`
      const attempts = item.results.map((result) => result.status)
      const outcome = item.outcome()
      if (
        identities.has(identity) ||
        item.results.length < 1 ||
        item.results.length > 2 ||
        item.results.some(
          (result, index) => !STATUSES.has(result.status) || result.retry !== index
        ) ||
        !STATUSES.has(item.expectedStatus) ||
        !OUTCOMES.has(outcome)
      ) {
        this.write("UE_LIVE_AUD154_V1 invalid\n")
        return
      }
      identities.add(identity)
      records.push({
        schema: 1,
        case_id: caseId,
        project,
        final_status: attempts.at(-1),
        expected_status: item.expectedStatus,
        outcome,
        attempts,
        retry: item.results.at(-1).retry,
        skipped: attempts.includes("skipped"),
      })
    }
    for (const record of records) this.write(`UE_LIVE_AUD154_V1 ${JSON.stringify(record)}\n`)
  }
}
