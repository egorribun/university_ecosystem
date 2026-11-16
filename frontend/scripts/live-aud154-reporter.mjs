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
const READ_CASE_FILE = fileURLToPath(
  new URL("../tests/e2e-live/messenger-unread-read.live.spec.ts", import.meta.url)
)
const READ_CASE_TITLE = "a real DM read receipt clears only that chat's unread state"
const READ_CASE_ID = "aud154-read-receipt"
const STATUSES = new Set(["passed", "failed", "timedOut", "skipped", "interrupted"])
const OUTCOMES = new Set(["expected", "unexpected", "flaky", "skipped"])

function caseIdFor(item) {
  const file = resolve(item.location.file)
  if (file === CASE_FILE && item.parent.title === "live messenger delivery") {
    return CASE_IDS.get(item.title)
  }
  if (file === READ_CASE_FILE && item.parent.type === "file" && item.title === READ_CASE_TITLE) {
    return READ_CASE_ID
  }
}

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
        (item) => caseIdFor(item) && ["desktop", "mobile"].includes(item.parent.project()?.name)
      )
  }

  onEnd() {
    const records = []
    const identities = new Set()
    let invalidRead = false
    for (const item of this.tests) {
      const project = item.parent.project().name
      const caseId = caseIdFor(item)
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
        if (caseId === READ_CASE_ID) {
          invalidRead = true
          continue
        }
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
    const completeRead =
      !invalidRead &&
      ["desktop", "mobile"].every((project) => identities.has(`${READ_CASE_ID}:${project}`))
    for (const record of records) {
      if (record.case_id !== READ_CASE_ID || completeRead) {
        this.write(`UE_LIVE_AUD154_V1 ${JSON.stringify(record)}\n`)
      }
    }
  }
}
