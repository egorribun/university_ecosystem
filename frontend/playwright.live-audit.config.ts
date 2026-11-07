import { defineConfig } from "@playwright/test"
import liveConfig from "./playwright.live.config.ts"
import { selectLiveAuditCasesFromEnvironment } from "./scripts/live-audit-case-selection.mjs"

const project = process.env.LIVE_AUDIT_PROJECT
if (project !== "desktop" && project !== "mobile") {
  throw new TypeError("the owned live audit config requires one closed project")
}
const selection = selectLiveAuditCasesFromEnvironment(process.env.LIVE_AUDIT_CASE_IDS, project)
if (!selection) throw new TypeError("the owned live audit config requires closed case IDs")

const exactTestFiles = selection.files.map((source) => {
  if (!source.startsWith("tests/")) {
    throw new TypeError("the live audit case map contains an invalid source")
  }
  return source.slice("tests/".length)
})
const availableProjects = liveConfig.projects
if (!Array.isArray(availableProjects)) {
  throw new TypeError("the base live config has no reviewed projects")
}
const selectedProjects = availableProjects.filter((project) =>
  selection.projects.includes(project.name)
)
if (selectedProjects.length !== selection.projects.length) {
  throw new TypeError("the live audit case map selected an unknown project")
}

export default defineConfig({
  ...liveConfig,
  testDir: "./tests",
  testMatch: exactTestFiles,
  grep: selection.grep,
  projects: selectedProjects,
})
