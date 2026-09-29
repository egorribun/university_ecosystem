import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { PassThrough } from "node:stream"
import test from "node:test"

import { pipeResponseBody } from "./server-response-stream.mjs"

test("pipeResponseBody completes a normal web response", async () => {
  const destination = new PassThrough()
  const chunks = []
  destination.on("data", (chunk) => chunks.push(chunk))

  await pipeResponseBody(new Response("complete"), destination)

  assert.equal(Buffer.concat(chunks).toString("utf8"), "complete")
  assert.equal(destination.writableFinished, true)
})

test("pipeResponseBody cancels the web stream when the client disconnects", async () => {
  let cancelReason
  const source = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode("partial"))
    },
    cancel(reason) {
      cancelReason = reason
    },
  })
  const destination = new PassThrough()
  destination.once("data", () => destination.destroy())

  await Promise.race([
    pipeResponseBody(new Response(source), destination),
    new Promise((_, reject) =>
      setTimeout(() => reject(new Error("stream cleanup timed out")), 1_000)
    ),
  ])

  assert.notEqual(cancelReason, undefined)
})

test("pipeResponseBody consumes a destination error without re-emitting it from the source", async () => {
  let cancelReason
  const logged = []
  const source = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode("partial"))
    },
    cancel(reason) {
      cancelReason = reason
    },
  })
  const destination = new PassThrough()
  destination.once("data", () => destination.emit("error", new Error("client write failed")))

  await pipeResponseBody(new Response(source), destination, {
    error: (...args) => logged.push(args),
  })

  await new Promise((resolve) => setImmediate(resolve))
  assert.equal(logged.length, 1)
  assert.match(logged[0][0], /destination stream error/u)
  assert.notEqual(cancelReason, undefined)
})

test("pipeResponseBody aborts the transport when the SSR source truncates", async () => {
  const logged = []
  const sourceFailure = new Error("render failed after headers")
  const source = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode("partial"))
      queueMicrotask(() => controller.error(sourceFailure))
    },
  })
  const destination = new PassThrough()

  await pipeResponseBody(new Response(source), destination, {
    error: (...args) => logged.push(args),
  })
  await new Promise((resolve) => setImmediate(resolve))

  assert.equal(destination.destroyed, true)
  assert.equal(destination.writableEnded, false, "a truncated SSR body must not look complete")
  assert.equal(destination.writableFinished, false, "a truncated SSR body must not finish cleanly")
  assert.equal(logged.length, 1)
  assert.equal(logged[0][1], sourceFailure)
})

test("the production frontend image copies every server runtime module", async () => {
  const dockerfile = await readFile(new URL("../../frontend.Dockerfile", import.meta.url), "utf8")

  for (const runtimeModule of [
    "frontend/scripts/server-prod.mjs",
    "frontend/scripts/contentTypes.mjs",
    "frontend/scripts/not-found-response.mjs",
    "frontend/scripts/lhci-ssr-response.mjs",
    "frontend/scripts/lhci-preview-mode.mjs",
    "frontend/scripts/server-response-stream.mjs",
    "frontend/scripts/server-readiness.mjs",
    "frontend/scripts/server-request-log.mjs",
    "frontend/scripts/server-static.mjs",
  ]) {
    assert.match(dockerfile, new RegExp(`COPY[^\\n]+${runtimeModule}`, "u"))
  }
})

test("every Docker npm ci stage enforces the reviewed lifecycle-script policy", async () => {
  const dockerfile = await readFile(new URL("../../frontend.Dockerfile", import.meta.url), "utf8")
  const npmCiCount = (dockerfile.match(/until npm ci/gu) ?? []).length
  const npmrcCopy = "COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./"
  const npmrcCopyCount = dockerfile.split(npmrcCopy).length - 1

  assert.equal(npmCiCount, 2)
  assert.equal(npmrcCopyCount, npmCiCount)
})

test("the production frontend image uses one immutable Node runtime across stages", async () => {
  const dockerfile = await readFile(new URL("../../frontend.Dockerfile", import.meta.url), "utf8")
  const nodeStages = [
    ...dockerfile.matchAll(/^FROM (node:24-alpine@sha256:[a-f0-9]{64}) AS (base|runtime)$/gmu),
  ]

  assert.equal(
    nodeStages.length,
    2,
    "base and runtime must both use a digest-pinned Node 24 Alpine image"
  )
  assert.equal(nodeStages[0][1], nodeStages[1][1], "build and runtime Node images must not drift")
  assert.deepEqual(
    nodeStages.map((match) => match[2]),
    ["base", "runtime"]
  )
})
