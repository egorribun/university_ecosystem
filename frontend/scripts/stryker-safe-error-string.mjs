/*
 * Stryker 10 / Vitest 4 error-transport compatibility preload.
 *
 * Patch only the pinned Stryker diagnostic formatter as Node loads that module.
 * Application/test String coercion, Error objects, and mutation statuses retain
 * their native behavior. A dependency update must explicitly revalidate this
 * adapter; unsupported versions or source changes stop the shard before tests.
 */
import { createHash } from "node:crypto"
import { readFileSync } from "node:fs"
import { registerHooks } from "node:module"

const expectedVersion = "10.0.0"
// Keep the public integrity digest as an auditable sha256sum record, following
// the repository's vendored-artifact checksum convention.
const checksumRecord = readFileSync(
  new URL("./stryker-util-errors.sha256", import.meta.url),
  "utf8"
)
const checksumMatch = /^([a-f0-9]{64}) {2}dist\/src\/errors\.js\n$/u.exec(checksumRecord)
if (!checksumMatch) {
  throw new Error("Stryker error formatter checksum record is malformed; revalidate the adapter")
}
const expectedSourceHash = checksumMatch[1]

export function rewriteStrykerErrorFormatter(source, metadata) {
  if (metadata.name !== "@stryker-mutator/util" || metadata.version !== expectedVersion) {
    throw new Error(
      "Stryker error adapter requires @stryker-mutator/util 10.0.0; revalidate the adapter"
    )
  }
  if (createHash("sha256").update(source).digest("hex") !== expectedSourceHash) {
    throw new Error("Stryker error formatter source changed; revalidate the adapter")
  }
  return (
    source.replace("return String(error);", "return formatStrykerErrorValue(error);") +
    `\nimport { formatStrykerErrorValue } from ${JSON.stringify(new URL("./stryker-error-formatter.mjs", import.meta.url).href)};\n`
  )
}

if (process.env.STRYKER_SHARD_RUN === "1") {
  const packageUrl = import.meta.resolve("@stryker-mutator/util/package.json")
  const metadata = JSON.parse(readFileSync(new URL(packageUrl), "utf8"))
  const targetUrl = new URL("./dist/src/errors.js", packageUrl).href
  rewriteStrykerErrorFormatter(readFileSync(new URL(targetUrl), "utf8"), metadata)
  let adapted = false
  registerHooks({
    load(url, context, nextLoad) {
      const loaded = nextLoad(url, context)
      if (url !== targetUrl) return loaded
      if (loaded.format !== "module") {
        throw new Error("Stryker error formatter module format changed; revalidate the adapter")
      }
      const source =
        typeof loaded.source === "string"
          ? loaded.source
          : Buffer.from(loaded.source).toString("utf8")
      const rewritten = rewriteStrykerErrorFormatter(source, metadata)
      adapted = true
      return { ...loaded, source: rewritten }
    },
  })
  // Ensure a prior NODE_OPTIONS preload did not cache the unadapted formatter.
  // errors.js has no imports or top-level effects in the pinned source.
  await import(targetUrl)
  if (!adapted) {
    throw new Error(
      "Stryker error formatter was loaded before its adapter; check NODE_OPTIONS order"
    )
  }
}
