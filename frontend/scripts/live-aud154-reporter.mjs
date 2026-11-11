import { resolve } from "node:path"
import process from "node:process"
import { fileURLToPath } from "node:url"

const CASE_TITLE =
  "a message is delivered, edited, and tombstoned in the other authenticated session"
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
          item.title === CASE_TITLE &&
          item.parent.title === "live messenger delivery" &&
          ["desktop", "mobile"].includes(item.parent.project()?.name)
      )
  }

  onEnd() {
    const records = []
    const projects = new Set()
    for (const item of this.tests) {
      const project = item.parent.project().name
      const attempts = item.results.map((result) => result.status)
      const outcome = item.outcome()
      if (
        projects.has(project) ||
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
      projects.add(project)
      records.push({
        schema: 1,
        case_id: "aud154-sent-confirmation",
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
