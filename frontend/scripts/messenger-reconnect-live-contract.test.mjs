import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import {
  cleanupMessengerReconnect,
  deleteOwnedMessengerMessage,
  withMessengerReconnectCleanup,
} from "../tests/e2e-live/messenger-reconnect-cleanup.mjs"

test("live messenger reconnect replays missed events exactly once and resumes in sequence", async () => {
  const spec = await readFile(
    new URL("../tests/e2e-live/messenger-reconnect.live.spec.ts", import.meta.url),
    "utf8"
  )
  const cleanupSource = await readFile(
    new URL("../tests/e2e-live/messenger-reconnect-cleanup.mjs", import.meta.url),
    "utf8"
  )

  const offline = spec.indexOf("setOffline(true)")
  const online = spec.indexOf("setOffline(false)")
  assert.ok(
    offline >= 0 && online > offline,
    "the real browser context must lose and restore network"
  )
  assert.match(spec, /socket\.on\(["']framesent["']/u)
  assert.match(spec, /socket\.on\(["']framereceived["']/u)
  assert.match(spec, /resume_token/u)
  assert.match(spec, /messages.*chatId|chatId.*messages/u)
  assert.match(spec, /toHaveCount\(1\)/u)
  assert.ok(
    /secondMemberSocket\s*=\s*observeSocket/u.test(spec),
    "a second authenticated group member must observe the live socket event"
  )
  const missedMessage = spec.indexOf("const missedWhileOfflineMessage = await sendMessage")
  assert.ok(
    offline >= 0 && missedMessage > offline && online > missedMessage,
    "the sender must publish a real message while the receiver context is offline"
  )
  assert.ok(
    /eventsForRoom\(\s*secondMemberSocket,\s*chatId,\s*missedWhileOfflineMessage\.id\)/u.test(spec),
    "a still-connected group member must observe the offline-period message before reconnect"
  )
  assert.ok(
    /expect\(historyRefetch\.ok\(\)\)\.toBe\(true\)/u.test(spec),
    "reconnection must also reconcile the missed message through the real history endpoint"
  )
  assert.ok(
    /receiverLog\.getByText\(missedWhileOfflineContent,\s*\{\s*exact:\s*true\s*\}\)\)\.toHaveCount\(1\)/u.test(
      spec
    ),
    "the replayed message must appear exactly once in the receiver's rendered history"
  )
  assert.ok(
    /expect\(missedDelivery\.replayed\)\.toBe\(true\)/u.test(spec),
    "the offline-period message must be observed as a replay frame"
  )
  assert.ok(
    /missedDelivery\.sequence\s*\?\?\s*0\)\.toBeGreaterThan\(initialDelivery\.sequence\s*\?\?\s*0/u.test(
      spec
    ),
    "the missed frame must advance the room sequence after the pre-disconnect frame"
  )
  assert.ok(
    /afterReconnectDelivery\.sequence\s*\?\?\s*0\)\.toBeGreaterThan\(\s*missedDelivery\.sequence\s*\?\?\s*0/u.test(
      spec
    ),
    "the post-reconnect live frame must follow the replayed frame"
  )
  assert.ok(
    /receives the next live message/u.test(spec),
    "the test must verify delivery resumes after reconnection"
  )
  assert.match(spec, /deleteOwnMessage/u)
  assert.match(cleanupSource, /const deadline = Date\.now\(\) \+ timeoutMs/u)
  assert.match(cleanupSource, /deleteButton\.click\(\{\s*timeout: remainingTimeout\(\)\s*\}\)/u)
  assert.match(cleanupSource, /await expectVisible\(dialog, remainingTimeout\(\)\)/u)
  assert.match(cleanupSource, /await expectCount\(message, 0, remainingTimeout\(\)\)/u)
  assert.match(
    cleanupSource,
    /if \(\(await deleteButton\.count\(\)\) === 0\) \{\s*throw new Error\("Owned message cleanup could not find the delete control\."\)\s*\}/u
  )
  assert.match(spec, /const runScenario = async/u)
  assert.match(spec, /await withMessengerReconnectCleanup\(\{\s*run: runScenario/u)
  assert.match(spec, /cleanup: \(\) =>\s*cleanupMessengerReconnect/u)
  assert.match(spec, /hasOwnerLog: ownerLog !== undefined/u)
  assert.match(spec, /deleteMessage: \(content, timeoutMs\) =>\s*deleteOwnMessage/u)
  assert.match(spec, /onCleanupFailure: \(description\) =>\s*\{\s*testInfo\.annotations\.push/u)
  assert.doesNotMatch(spec, /catch\s*\{\s*\/\/ Best-effort cleanup/u)
  assert.match(spec, /trace:\s*["']off["']/u)
  assert.match(spec, /screenshot:\s*["']off["']/u)
  assert.doesNotMatch(spec, /routeWebSocket|WebSocket\s*=\s*new\s+Mock/u)
})

test("a visible owned message without a delete control fails with a sanitized error", async () => {
  const privateContent = "private-chat-body-that-must-not-appear"
  const selectorCalls = []
  const deleteButton = { count: async () => 0 }
  const row = {
    getByRole(role, options) {
      selectorCalls.push(["delete-control", role, options])
      return deleteButton
    },
  }
  const message = {
    count: async () => 1,
    locator(selector) {
      selectorCalls.push(["message-row", selector])
      return row
    },
  }
  const log = {
    getByText(content, options) {
      selectorCalls.push(["message", content, options])
      return message
    },
  }
  let pageCalls = 0

  await assert.rejects(
    deleteOwnedMessengerMessage({
      page: {
        getByRole() {
          pageCalls += 1
          throw new Error("dialog lookup must not be reached")
        },
      },
      log,
      content: privateContent,
      timeoutMs: 100,
      async expectVisible() {
        throw new Error("visibility check must not be reached")
      },
      async expectCount() {
        throw new Error("count check must not be reached")
      },
    }),
    (error) => {
      assert.ok(error instanceof Error)
      assert.equal(error.message, "Owned message cleanup could not find the delete control.")
      assert.doesNotMatch(error.message, /private-chat-body|access_token|private-cleanup-token/u)
      return true
    }
  )

  assert.deepEqual(selectorCalls, [
    ["message", privateContent, { exact: true }],
    [
      "message-row",
      "xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' group ')][1]",
    ],
    ["delete-control", "button", { name: "Удалить сообщение", exact: true }],
  ])
  assert.equal(pageCalls, 0)
})

test("an already absent owned message is an idempotent cleanup success", async () => {
  let rowLookups = 0
  const log = {
    getByText(content, options) {
      assert.equal(content, "owned-message-already-absent")
      assert.deepEqual(options, { exact: true })
      return {
        count: async () => 0,
        locator() {
          rowLookups += 1
          throw new Error("an absent message has no row to inspect")
        },
      }
    },
  }

  await deleteOwnedMessengerMessage({
    page: {
      getByRole() {
        throw new Error("an absent message has no dialog")
      },
    },
    log,
    content: "owned-message-already-absent",
    timeoutMs: 100,
    async expectVisible() {
      throw new Error("an absent message has no dialog")
    },
    async expectCount() {
      throw new Error("an absent message needs no count assertion")
    },
  })
  assert.equal(rowLookups, 0)
})

test("an expired owned-message deadline fails before clicking delete", async () => {
  let deleteClicks = 0
  const deleteButton = {
    count: async () => 1,
    async click() {
      deleteClicks += 1
    },
  }
  const message = {
    count: async () => 1,
    locator() {
      return {
        getByRole() {
          return deleteButton
        },
      }
    },
  }

  await assert.rejects(
    deleteOwnedMessengerMessage({
      page: {
        getByRole() {
          throw new Error("expired deadline must stop before dialog lookup")
        },
      },
      log: {
        getByText() {
          return message
        },
      },
      content: "private-message-content",
      timeoutMs: 0,
      async expectVisible() {
        throw new Error("expired deadline must stop before visibility")
      },
      async expectCount() {
        throw new Error("expired deadline must stop before count assertion")
      },
    }),
    (error) => error instanceof Error && error.message === "Owned message cleanup deadline expired"
  )
  assert.equal(deleteClicks, 0)
})

test("owned message deletion uses the dialog and verifies the message is gone", async () => {
  let messagePresent = true
  const actions = []
  const message = {
    count: async () => (messagePresent ? 1 : 0),
    locator(selector) {
      assert.match(selector, /^xpath=/u)
      return row
    },
  }
  const deleteButton = {
    count: async () => 1,
    async click(options) {
      assert.ok(options.timeout > 0)
      actions.push("open-delete-dialog")
    },
  }
  const confirmButton = {
    async click(options) {
      assert.ok(options.timeout > 0)
      actions.push("confirm-delete")
      messagePresent = false
    },
  }
  const row = {
    getByRole(role, options) {
      assert.equal(role, "button")
      assert.deepEqual(options, { name: "Удалить сообщение", exact: true })
      return deleteButton
    },
  }
  const dialog = {
    getByRole(role, options) {
      assert.equal(role, "button")
      assert.deepEqual(options, { name: "Удалить", exact: true })
      return confirmButton
    },
  }
  const log = {
    getByText(content, options) {
      assert.equal(content, "owned-message-to-delete")
      assert.deepEqual(options, { exact: true })
      return message
    },
  }

  await deleteOwnedMessengerMessage({
    page: {
      getByRole(role, options) {
        assert.equal(role, "alertdialog")
        assert.deepEqual(options, { name: "Удалить сообщение" })
        return dialog
      },
    },
    log,
    content: "owned-message-to-delete",
    timeoutMs: 100,
    async expectVisible(locator, timeout) {
      assert.equal(locator, dialog)
      assert.ok(timeout > 0)
      actions.push("dialog-visible")
    },
    async expectCount(locator, count, timeout) {
      assert.equal(locator, message)
      assert.equal(count, 0)
      assert.ok(timeout > 0)
      assert.equal(messagePresent, false)
      actions.push("message-removed")
    },
  })

  assert.deepEqual(actions, [
    "open-delete-dialog",
    "dialog-visible",
    "confirm-delete",
    "message-removed",
  ])
})

test("owned message and context cleanup failures are counted without exposing error data", async () => {
  const privateContent = "private-chat-body-that-must-not-appear"
  const privateError = "access_token=private-cleanup-token"
  const deleted = []
  const closed = []
  const cleanupFailure = await cleanupMessengerReconnect({
    hasOwnerLog: true,
    createdMessages: [privateContent, "another-private-message"],
    deleteMessage: async (content) => {
      deleted.push(content)
      if (content === privateContent) throw new Error(privateError)
    },
    contexts: [
      {
        async close() {
          closed.push("failed")
          throw new Error(privateError)
        },
      },
      {
        async close() {
          closed.push("closed")
        },
      },
    ],
    timeoutMs: 100,
  })

  assert.deepEqual(deleted, [privateContent, "another-private-message"])
  assert.deepEqual(closed, ["failed", "closed"])
  assert.equal(
    cleanupFailure,
    "Messenger reconnect cleanup failed within 100 ms: 1 sender-owned message could not be deleted; 1 isolated browser context could not be closed."
  )
  assert.doesNotMatch(cleanupFailure, /private-chat-body|access_token|private-cleanup-token/u)
})

test("cleanup skips message deletion without an owner log and still closes every context", async () => {
  let deleteCalls = 0
  let closeCalls = 0
  const cleanupFailure = await cleanupMessengerReconnect({
    hasOwnerLog: false,
    createdMessages: ["private-chat-body"],
    deleteMessage: async () => {
      deleteCalls += 1
    },
    contexts: [
      {
        async close() {
          closeCalls += 1
        },
      },
      {
        async close() {
          closeCalls += 1
        },
      },
    ],
  })

  assert.equal(deleteCalls, 0)
  assert.equal(closeCalls, 2)
  assert.equal(cleanupFailure, null)
  const scenarioResult = await withMessengerReconnectCleanup({
    run: async () => undefined,
    cleanup: async () => cleanupFailure,
  })
  assert.equal(scenarioResult, undefined)
})

test("expired cleanup deadline counts remaining owned messages", async () => {
  let deleteCalls = 0
  let closeCalls = 0
  const cleanupFailure = await cleanupMessengerReconnect({
    hasOwnerLog: true,
    createdMessages: ["first-private-message", "second-private-message"],
    deleteMessage: async () => {
      deleteCalls += 1
    },
    contexts: [
      {
        async close() {
          closeCalls += 1
        },
      },
    ],
    timeoutMs: 0,
  })

  assert.equal(deleteCalls, 0)
  assert.equal(closeCalls, 1)
  assert.equal(
    cleanupFailure,
    "Messenger reconnect cleanup failed within 0 ms: 2 sender-owned messages could not be deleted."
  )
})

test("cleanup attempts finish within one shared deadline", async () => {
  let deleteCalls = 0
  let closeCalls = 0
  const neverSettles = () => new Promise(() => {})
  const startedAt = Date.now()
  const cleanupFailure = await cleanupMessengerReconnect({
    hasOwnerLog: true,
    createdMessages: ["first-private-message", "second-private-message"],
    deleteMessage: async () => {
      deleteCalls += 1
      return neverSettles()
    },
    contexts: [
      {
        close() {
          closeCalls += 1
          return neverSettles()
        },
      },
      {
        close() {
          closeCalls += 1
          return neverSettles()
        },
      },
    ],
    timeoutMs: 30,
  })

  assert.equal(deleteCalls, 2)
  assert.equal(closeCalls, 2)
  assert.ok(Date.now() - startedAt < 500)
  assert.equal(
    cleanupFailure,
    "Messenger reconnect cleanup failed within 30 ms: 2 sender-owned messages could not be deleted; 2 isolated browser contexts could not be closed."
  )
})

test("cleanup failure is reported without replacing the primary test failure", async () => {
  const primaryFailure = new Error("primary assertion failed")
  const cleanupFailure =
    "Messenger reconnect cleanup failed within 30 ms: 1 sender-owned message could not be deleted."
  const annotations = []

  await assert.rejects(
    withMessengerReconnectCleanup({
      async run() {
        throw primaryFailure
      },
      async cleanup() {
        return cleanupFailure
      },
      onCleanupFailure(description) {
        annotations.push(description)
      },
    }),
    (error) => error === primaryFailure
  )
  assert.deepEqual(annotations, [cleanupFailure])
})

test("cleanup-only failure is actionable and reporter errors do not replace it", async () => {
  const cleanupFailure = "Messenger reconnect cleanup could not complete."

  await assert.rejects(
    withMessengerReconnectCleanup({
      async run() {},
      async cleanup() {
        throw new Error("access_token=private-cleanup-token")
      },
      onCleanupFailure() {
        throw new Error("reporter token=private-cleanup-token")
      },
    }),
    (error) => error instanceof Error && error.message === cleanupFailure
  )
})
