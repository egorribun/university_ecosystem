import "./run-stryker-progress.test.mjs"
import "./run-stryker-process.test.mjs"
import "./run-stryker-planning.test.mjs"
import "./run-stryker-shard-history.test.mjs"
import "./run-stryker-shard-publication.test.mjs"
import assert from "node:assert/strict"
import test from "node:test"

const runnerUrl = new URL("./run-stryker.mjs", import.meta.url)
test("release eligibility requires a clean exact-SHA workflow run and attempt", async () => {
  const { isMutationRunReleaseEligible, isReleaseEligible } = await import(runnerUrl)
  const headSha = "a".repeat(40)
  const identity = { headSha, repositoryDirty: false }
  const complete = {
    GITHUB_RUN_ID: "42",
    GITHUB_RUN_ATTEMPT: "3",
    GITHUB_SHA: headSha,
  }

  assert.equal(isReleaseEligible(identity, complete), true)
  assert.equal(isReleaseEligible({ ...identity, repositoryDirty: true }, complete), false)
  assert.equal(isReleaseEligible(identity, { ...complete, GITHUB_RUN_ATTEMPT: "" }), false)
  assert.equal(isReleaseEligible(identity, { ...complete, GITHUB_RUN_ATTEMPT: undefined }), false)
  assert.equal(isReleaseEligible(identity, { ...complete, GITHUB_SHA: "b".repeat(40) }), false)
  assert.equal(isMutationRunReleaseEligible(identity, false, complete), true)
  assert.equal(isMutationRunReleaseEligible(identity, true, complete), false)
})
