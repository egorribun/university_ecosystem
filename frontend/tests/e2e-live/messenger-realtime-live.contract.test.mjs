import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import ts from "typescript"
import { URL } from "node:url"

const specUrl = new URL("./messenger-realtime.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)

const [spec, config] = await Promise.all([readFile(specUrl, "utf8"), readFile(configUrl, "utf8")])

test("live Messenger realtime acceptance runs on desktop and mobile without saved credentials", () => {
  assert.match(config, /testDir:\s*["']\.\/tests\/e2e-live["']/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
  assert.match(config, /name:\s*["']desktop["']/u)
  assert.match(config, /name:\s*["']mobile["']/u)
  assert.match(config, /viewport:\s*\{\s*width:\s*1440,\s*height:\s*900\s*\}/u)
  assert.match(config, /viewport:\s*\{\s*width:\s*390,\s*height:\s*844\s*\}/u)
  assert.match(spec, /test\.use\(\{\s*trace:\s*["']off["'],\s*screenshot:\s*["']off["']\s*\}\)/u)
  assert.match(config, /video:\s*["']off["']/u)
  assert.match(spec, /process\.env\.LIVE_BASE_URL/u)
  assert.doesNotMatch(spec, /console\.(?:log|info|debug)\(/u)
})

test("each realtime flow uses independent, differently authenticated student and teacher contexts", () => {
  assert.match(spec, /browser\.newContext\(/u)
  assert.match(spec, /receiverContext\.newPage\(\)/u)
  assert.match(spec, /await loginAs\(page, ["']student["']\)/u)
  assert.match(spec, /await loginAs\(receiverPage, ["']teacher["']\)/u)
  assert.match(spec, /crypto\.randomUUID\(\)/u)
  assert.match(spec, /\/api\/v1\/users\/me/u)
  assert.match(spec, /expect\(student\.role\)\.toBe\(["']student["']\)/u)
  assert.match(spec, /expect\(teacher\.role\)\.toBe\(["']teacher["']\)/u)
  assert.match(spec, /expect\(receiver\.id\)\.not\.toBe\(sender\.id\)/u)
  assert.match(spec, /expect\(teacher\.id\)\.not\.toBe\(student\.id\)/u)
})

test("message, edit, delete, and reaction assertions observe real server responses and WebSocket frames", () => {
  assert.match(spec, /page\.on\(["']websocket["']/u)
  assert.match(spec, /socket\.on\(["']framesent["']/u)
  assert.match(spec, /socket\.on\(["']framereceived["']/u)
  assert.match(spec, /hasRoomJoin\(parseFrame\(payload\), chatId\)/u)
  assert.match(
    spec,
    /new URL\(response\.url\(\)\)\.pathname === `\/api\/v1\/chats\/\$\{chatId\}\/messages`/u
  )
  assert.match(spec, /sender_id:\s*student\.id/u)
  assert.match(
    spec,
    /sender_id:\s*student\.id[\s\S]*?message:\s*\{[\s\S]*?senderId:\s*student\.id/u
  )
  assert.match(
    spec,
    /expect\(receiverMessages\)\.toContainEqual\(expect\.objectContaining\(expectedFrame\)\)/u
  )
  assert.match(spec, /expect\(renderedMessage\)\.toHaveCount\(1\)/u)
  assert.match(spec, /type === "message_edited"[\s\S]*?type === "message_deleted"/u)
  assert.match(spec, /request\.method\(\) === "PATCH"/u)
  assert.match(spec, /request\.method\(\) === "DELETE"/u)
  assert.match(spec, /senderReactions\.filter\([\s\S]*?frame\.userId === receiver\.id/u)
  assert.match(spec, /senderMessageHistory\?\.reactions/u)
  assert.match(spec, /receiverMessageHistory\?\.reactions/u)
})

test("deleted message tombstones keep authorized history visible without reaction controls", () => {
  const tombstoneStart = spec.indexOf(
    'test("a message is delivered, edited, and tombstoned in the other authenticated session"'
  )
  assert.notEqual(tombstoneStart, -1, "the tombstone scenario must remain explicit")
  const nextScenario = spec.indexOf(
    'test("direct-message replay stays ordered and exactly once across receiver reconnect',
    tombstoneStart
  )
  assert.notEqual(nextScenario, -1, "the tombstone scenario boundary must remain explicit")
  const tombstoneScenario = spec.slice(tombstoneStart, nextScenario)

  assert.match(tombstoneScenario, /request\.method\(\) === "POST"[\s\S]*?\/reactions/u)
  assert.match(
    tombstoneScenario,
    /getByRole\("button", \{ name: "Отреагировать 👍", exact: true \}\)/u
  )
  assert.match(
    tombstoneScenario,
    /const tombstone = messageLog\.getByText\("Сообщение удалено", \{ exact: true \}\)[\s\S]{0,100}await expect\(tombstone\)\.toBeVisible\(\)/u
  )
  assert.match(
    tombstoneScenario,
    /tombstoneRow\.getByRole\("button", \{ name: \/реакци\/i \}\)[\s\S]{0,100}\.toHaveCount\(0\)/u
  )
  assert.match(
    tombstoneScenario,
    /page\.request\.get\(`\/api\/v1\/chats\/\$\{chatId\}\/messages\?limit=50`\)/u
  )
  assert.match(
    tombstoneScenario,
    /receiverPage\.request\.get\(`\/api\/v1\/chats\/\$\{chatId\}\/messages\?limit=50`\)/u
  )
  assert.match(tombstoneScenario, /deleted_at:\s*string \| null/u)
  assert.match(
    tombstoneScenario,
    /expect\(senderTombstone\)\.toMatchObject\(\{ id: sentMessage\.id, content: "" \}\)/u
  )
  assert.match(tombstoneScenario, /expect\(senderTombstone\?\.deleted_at\)\.toBeTruthy\(\)/u)
  assert.match(
    tombstoneScenario,
    /expect\(receiverTombstone\)\.toMatchObject\(\{ id: sentMessage\.id, content: "" \}\)/u
  )
  assert.match(tombstoneScenario, /expect\(receiverTombstone\?\.deleted_at\)\.toBeTruthy\(\)/u)
  assert.match(tombstoneScenario, /senderTombstone\?\.reactions/u)
  assert.match(tombstoneScenario, /receiverTombstone\?\.reactions/u)
})

test("removing a reaction is delivered over WebSocket and clears both members' server history", () => {
  const reactionStart = spec.indexOf(
    'test("a receiver reaction is delivered to the sender over the live WebSocket"'
  )
  assert.notEqual(reactionStart, -1, "the reaction scenario must remain explicit")
  const replyStart = spec.indexOf(
    'test("a sender reply preserves its parent identity',
    reactionStart
  )
  assert.notEqual(replyStart, -1, "the following scenario boundary must remain explicit")
  const reactionScenario = spec.slice(reactionStart, replyStart)
  assert.match(reactionScenario, /frame\.action === "removed"/u)
  assert.match(reactionScenario, /senderAfterRemovalHistory[\s\S]{0,220}toEqual\(\[\]\)/u)
  assert.match(reactionScenario, /receiverAfterRemovalHistory[\s\S]{0,220}toEqual\(\[\]\)/u)
})

test("failed UI message creates emit only a closed status before the existing assertion", () => {
  const start = spec.indexOf("async function sendLiveMessage(")
  const end = spec.indexOf("async function deleteOwnedLiveMessage(", start)
  assert.ok(start >= 0 && end > start)
  const helper = spec.slice(start, end)
  const failedCheck = helper.indexOf("if (!response.ok()) {")
  const diagnostic = helper.indexOf(
    'reportLiveHttpStatus(project, "messenger-message-send", response.status())'
  )
  const assertion = helper.indexOf("expect(response.ok()).toBe(true)")
  assert.ok(failedCheck >= 0 && failedCheck < diagnostic && diagnostic < assertion)
  const diagnosticBlock = helper.slice(failedCheck, assertion)
  assert.doesNotMatch(diagnosticBlock, /response\.(?:url|headers|json|text)\s*\(/u)
  for (const content of [
    "live-dm-order-first",
    "live-dm-order-second",
    "live-dm-reconnect-missed",
    "live-dm-reconnect-after",
    "messageContent",
    "parentContent",
    "sourceContent",
  ]) {
    assert.ok(spec.includes(content), "existing send scenarios remain present")
  }
  for (const [response, promise] of [
    ["messageResponse", "messageResponsePromise"],
    ["replyResponse", "replyResponsePromise"],
  ]) {
    const awaited = spec.indexOf("const " + response + " = await " + promise)
    const diagnosticBlockStart = spec.indexOf("if (!" + response + ".ok()) {", awaited)
    const statusCheck = spec.indexOf('"messenger-message-send"', diagnosticBlockStart)
    const assertion = spec.indexOf("expect(" + response + ".ok()).toBe(true)", diagnosticBlockStart)
    assert.ok(awaited >= 0 && diagnosticBlockStart > awaited)
    assert.ok(statusCheck > diagnosticBlockStart && assertion > statusCheck)
  }
})

test("ordered live deliveries remain exactly once across reconnect and history refresh", () => {
  assert.match(
    spec,
    /direct-message replay stays ordered and exactly once across receiver reconnect/u
  )
  assert.match(spec, /const messageIds = \[first\.id, second\.id\]/u)
  assert.match(
    spec,
    /orderedDeliveries\.map\(\(frame\) => frame\.message\.id\)\)\.toEqual\(messageIds\)/u
  )
  assert.match(spec, /expect\(firstSequence\)\.toBeLessThan\(secondSequence\)/u)
  assert.match(spec, /await receiverContext\.setOffline\(true\)/u)
  assert.match(spec, /await receiverContext\.setOffline\(false\)/u)
  assert.match(spec, /historyRefetchPromise/u)
  assert.match(spec, /expect\(allTestDeliveries\)\.toHaveLength\(expectedMessageIds\.length\)/u)
  assert.match(
    spec,
    /receiverLog\.getByText\(message\.content, \{ exact: true \}\)\)\.toHaveCount\(1\)/u
  )
  assert.match(spec, /const missedWhileOffline = await sendLiveMessage/u)
  assert.match(
    spec,
    /receiverContext\.setOffline\(true\)[\s\S]*?missedWhileOffline[\s\S]*?receiverContext\.setOffline\(false\)/u
  )
  assert.match(spec, /expect\(missedDelivery\.replayed\)\.toBe\(true\)/u)
  assert.match(spec, /expect\(secondSequence\)\.toBeLessThan\(missedSequence\)/u)
  assert.match(spec, /expect\(missedSequence\)\.toBeLessThan\(afterReconnectSequence\)/u)
  assert.match(
    spec,
    /expectedMessageIds = \[first\.id, second\.id, missedWhileOffline\.id, afterReconnect\.id\]/u
  )
  assert.match(spec, /expect\(allTestDeliveries\)\.toHaveLength\(expectedMessageIds\.length\)/u)
})

test("reply and forward live events retain their server-owned relationship metadata", () => {
  assert.match(spec, /a sender reply preserves its parent identity and reaches the receiver/u)
  assert.match(spec, /reply_to:\s*\{\s*id:\s*createdParent\.id/u)
  assert.match(spec, /frame\.message\.replyToId === createdParent\.id/u)
  assert.match(
    spec,
    /forwarding through the current-chat modal preserves attribution and reaches the receiver/u
  )
  assert.match(spec, /forwarded_from_name:\s*senderName/u)
  assert.match(spec, /frame\.message\.forwardedFromName === senderName/u)
  const forwardingStart = spec.indexOf('test("forwarding through the current-chat modal')
  assert.notEqual(forwardingStart, -1, "forwarding scenario must remain explicit")
  const forwardingScenario = spec.slice(forwardingStart)
  assert.match(forwardingScenario, /receiverMessages\.filter\(/u)
  assert.match(forwardingScenario, /frame\.message\.id === createdForward\.id/u)
  assert.match(forwardingScenario, /\.toHaveLength\(1\)/u)
})

test("cleanup deletes only exact sender-owned test messages and never a reusable seeded chat", () => {
  assert.match(spec, /async function deleteOwnedLiveMessage\([\s\S]*?message: CreatedLiveMessage/u)
  assert.match(spec, /`\/api\/v1\/chats\/\$\{chatId\}\/messages\/\$\{message\.id\}`/u)
  assert.match(
    spec,
    /async function deleteOwnedForwardedLiveMessage\([\s\S]*?message: CreatedLiveMessage/u
  )
  assert.match(spec, /`\/api\/v1\/chats\/\$\{chatId\}\/messages\/\$\{message\.id\}`/u)
  assert.match(
    spec,
    /for \(const message of createdMessages\)[\s\S]*?deleteOwnedLiveMessage\(page, senderLog, chatId, message\)/u
  )
  assert.match(spec, /receiverContext\.close\(\)/u)
  assert.doesNotMatch(spec, /DELETE[^\n]*\/api\/v1\/chats\/\$\{chatId\}(?:["'`]|\s)/u)
  assert.doesNotMatch(spec, /page\.route\(|routeWebSocket\(|route\.fulfill\(|useMockApi/u)
})

test("the live typing scenario observes the peer socket and the rendered expiring indicator", () => {
  const start = spec.indexOf(
    'test("a peer typing indicator appears and expires over the live socket"'
  )
  assert.notEqual(start, -1)
  const scenario = spec.slice(start)
  assert.match(scenario, /await loginAs\(page, "student"\)/u)
  assert.match(scenario, /await loginAs\(receiverPage, "teacher"\)/u)
  assert.match(scenario, /hasRoomJoin\(frame, activeChatId\)/u)
  assert.match(scenario, /frame\.type === "heartbeat_ping"/u)
  assert.match(scenario, /frame\.type === "heartbeat_pong"/u)
  assert.match(scenario, /receiverSessions\.some\(\(session\) => session\.acknowledged/u)
  assert.match(scenario, /\/api\/v1\/chats\/\$\{activeChatId\}\/typing/u)
  assert.match(scenario, /page\.locator\("#chat-message-input"\)\.fill\(draft\)/u)
  assert.match(scenario, /event\.type === "typing"/u)
  assert.match(scenario, /event\.chat_id === activeChatId/u)
  assert.match(scenario, /event\.user_id === student\.id/u)
  assert.match(scenario, /new MutationObserver\(/u)
  assert.match(scenario, /\[role="status"\]\[aria-live="polite"\]/u)
  assert.match(scenario, /getBoundingClientRect\(\)/u)
  assert.match(scenario, /observation\.appearedAt = performance\.now\(\)/u)
  assert.match(scenario, /observation\.removedAt = performance\.now\(\)/u)
  assert.match(scenario, /expect\(observation\?\.text\)\.toContain/u)
  assert.match(scenario, /socketOpenAtReceipt: !socket\.isClosed\(\)/u)
  assert.match(scenario, /expect\(receiverSession\.socket\.isClosed\(\)\)\.toBe\(false\)/u)
  assert.doesNotMatch(scenario, /dispatchEvent|MessageEvent|routeWebSocket|route\.fulfill/u)
})

// Parse source only: importing the live spec would register browser work.
function enterScenario(sourceText) {
  const source = ts.createSourceFile("messenger.ts", sourceText, ts.ScriptTarget.Latest, true)
  assert.equal(source.parseDiagnostics.length, 0)
  const matches = []
  function visit(node) {
    if (
      ts.isCallExpression(node) &&
      node.expression.getText(source) === "test" &&
      node.arguments[0]?.text === "shows sent confirmation after the server accepts the message"
    )
      matches.push(node)
    ts.forEachChild(node, visit)
  }
  visit(source)
  assert.equal(matches.length, 1, "the named Enter case must be unique")
  const callback = matches[0].arguments[1]
  const body = callback.body.statements.find(ts.isTryStatement)?.tryBlock
  assert.ok(body, "the case keeps its cleanup-protected body")
  const printer = ts.createPrinter({ removeComments: true })
  const print = (node) => printer.printNode(ts.EmitHint.Unspecified, node, source).trim()
  return { source, body, print }
}

function assertEnterSenderContract(sourceText) {
  const { body, print } = enterScenario(sourceText)
  const statements = [...body.statements]
  const texts = statements.map(print)
  const find = (pattern) => {
    const index = texts.findIndex((text) => pattern.test(text))
    assert.notEqual(index, -1, `missing Enter assertion: ${pattern}`)
    return index
  }
  const input = find(
    /^const input = page\.getByRole\("textbox", \{ name: \/message\|сообщение\/i \}\);$/u
  )
  const fill = find(/^await input\.fill\(message\);$/u)
  const press = find(/^await input\.press\("Enter"\);$/u)
  assert.ok(input < fill && fill < press, "fill and Enter use the accessible textbox")
  const accepted = find(/^expect\(created\.content\)\.toBe\(message\);$/u)
  const sender = find(/^const senderText = senderLog\.getByText\(message, \{ exact: true \}\);$/u)
  assert.equal(sender, accepted + 1, "sender observation starts immediately after POST validation")
  const response = find(/^const messageResponse = await messageResponsePromise;$/u)
  assert.equal(response, press + 1, "await the response immediately after Enter")
  assert.ok(response < accepted)
  const pendingWork = []
  function collectAwaits(node) {
    assert.ok(
      !(ts.isForOfStatement(node) && node.awaitModifier),
      "asynchronous iteration is forbidden in the critical window"
    )
    if (ts.isAwaitExpression(node)) pendingWork.push(node)
    ts.forEachChild(node, collectAwaits)
  }
  for (const statement of statements.slice(response + 1, sender)) collectAwaits(statement)
  assert.equal(
    pendingWork.length,
    1,
    "only response JSON may be awaited before sender observations"
  )
  assert.equal(print(pendingWork[0].expression), "messageResponse.json()")
  const jsonDeclaration = pendingWork[0].parent.parent.parent
  assert.ok(ts.isVariableDeclaration(jsonDeclaration))
  assert.equal(
    jsonDeclaration.name.getText(),
    "created",
    "the awaited JSON supplies accepted content"
  )

  const visible = find(/^await expect\(senderText\)\.toBeVisible\(/u)
  const row = find(/^const senderRow = senderText\.locator\(/u)
  const status = find(/^await expect\(senderRow\.getByRole\("img",/u)
  assert.equal(visible, sender + 1, "no extra count or receiver wait before sender visibility")
  assert.equal(row, visible + 1)
  assert.equal(status, row + 1, "no extra wait before scoped sender status")
  const allowedAwaits = [
    statements[response].declarationList.declarations[0].initializer,
    pendingWork[0],
    statements[visible].expression,
    statements[status].expression,
  ]
  assert.ok(allowedAwaits.every(ts.isAwaitExpression))
  pendingWork.length = 0
  for (const statement of statements.slice(press + 1, status + 1)) collectAwaits(statement)
  assert.ok(
    pendingWork.length === allowedAwaits.length &&
      pendingWork.every((node, index) => node === allowedAwaits[index]),
    "only the response, JSON, visibility and status awaits are allowed in the critical window"
  )
  assert.ok(
    texts[row].includes(
      "xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' group ')][1]"
    )
  )
  assert.ok(
    texts[status].includes("/^(Отправлено|Прочитано получателем|Sent|Read by recipient)$/u")
  )
  for (const [index, budget] of [
    [visible, 5000],
    [status, 10000],
  ]) {
    const call = statements[index].expression.expression
    assert.ok(ts.isCallExpression(call))
    assert.equal(call.expression.name?.text, "toBeVisible", "sender status must be visible")
    const options = call.arguments[0]
    assert.ok(
      options && ts.isObjectLiteralExpression(options),
      "explicit historical timeout required"
    )
    assert.equal(call.arguments.length, 1)
    assert.equal(
      options.properties.length,
      1,
      "timeout options cannot override or spread properties"
    )
    const timeout = options.properties[0]
    assert.ok(ts.isPropertyAssignment(timeout), "timeout must be a direct literal property")
    assert.equal(timeout.name.getText(), "timeout")
    assert.ok(timeout && ts.isNumericLiteral(timeout.initializer), "literal timeout required")
    assert.equal(Number(timeout.initializer.text), budget, "retain the historical timeout budget")
  }
  const count = find(/^await expect\(senderText\)\.toHaveCount\(1\);$/u)
  assert.ok(count > status, "uniqueness must not extend sender visibility or status deadlines")
  const receiver = find(/^await expect\.poll\(/u)
  // Pre-send room readiness is intentional; inspect only awaits after acceptance.
  assert.ok(receiver < accepted)
  for (let index = accepted + 1; index <= status; index++) {
    assert.doesNotMatch(texts[index], /receiver/u, "sender budgets precede receiver delivery waits")
  }
}

test("Enter preserves accessible input and immediate historical sender assertion budgets", () => {
  assertEnterSenderContract(spec)
})

test("Enter sender contract rejects weakened disposable source variants", () => {
  const { body, print } = enterScenario(spec)
  const senderStart = [...body.statements].find((node) =>
    print(node).startsWith("const senderText =")
  )
  const count = [...body.statements].find((node) =>
    print(node).startsWith("await expect(senderText).toHaveCount")
  )
  const block = spec.slice(senderStart.getStart(), count.end)
  const variants = [
    [
      "ID-only input",
      spec.replace(
        'page.getByRole("textbox", { name: /message|сообщение/i })',
        'page.locator("#chat-message-input")'
      ),
    ],
    ["wrong accessible name", spec.replace("/message|сообщение/i", "/unrelated/i")],
    [
      "different Enter input",
      spec.replace(
        'await input.press("Enter")',
        'await page.locator("#chat-message-input").press("Enter")'
      ),
    ],
    [
      "looser bubble budget",
      spec.replace(
        "senderText).toBeVisible({ timeout: 5_000 })",
        "senderText).toBeVisible({ timeout: 15_000 })"
      ),
    ],
    [
      "inherited bubble budget",
      spec.replace("senderText).toBeVisible({ timeout: 5_000 })", "senderText).toBeVisible()"),
    ],
    [
      "looser status budget",
      spec.replace(").toBeVisible({ timeout: 10_000 })", ").toBeVisible({ timeout: 15_000 })"),
    ],
    [
      "inherited status budget",
      spec.replace(").toBeVisible({ timeout: 10_000 })", ").toBeVisible()"),
    ],
    [
      "hidden status assertion",
      spec.replace(").toBeVisible({ timeout: 10_000 })", ").toBeHidden({ timeout: 10_000 })"),
    ],
    ["missing uniqueness", spec.replace("await expect(senderText).toHaveCount(1)", "")],
    [
      "count before status",
      spec.replace(
        block,
        block
          .replace("await expect(senderText).toHaveCount(1)", "")
          .replace(
            "const senderRow =",
            "await expect(senderText).toHaveCount(1)\n      const senderRow ="
          )
      ),
    ],
    [
      "count before bubble",
      spec.replace(
        block,
        block
          .replace("await expect(senderText).toHaveCount(1)", "")
          .replace(
            "await expect(senderText).toBeVisible",
            "await expect(senderText).toHaveCount(1)\n      await expect(senderText).toBeVisible"
          )
      ),
    ],
    [
      "receiver before sender",
      spec
        .replace(block, "")
        .replace(
          "await expect(renderedMessage).toBeVisible()",
          "await expect(renderedMessage).toBeVisible()\n" + block
        ),
    ],
  ]
  for (const [name, candidate] of variants) {
    assert.ok(candidate !== spec, `${name} mutation must alter source`)
    enterScenario(candidate) // A negative control must remain syntactically valid.
    assert.throws(() => assertEnterSenderContract(candidate), { name: "AssertionError" }, name)
  }
})

test("Enter sender contract tolerates formatting, comments and numeric separators", () => {
  assertEnterSenderContract(
    spec
      .replace("timeout: 5_000", "timeout: 5000")
      .replace(
        "const senderText = senderLog",
        "// Sender observations must stay before peer waits.\n      const senderText = senderLog"
      )
  )
})

for (const [name, original, replacement] of [
  [
    "receiver delay after Enter",
    'await input.press("Enter")',
    'await input.press("Enter")\n      await receiverPage.waitForTimeout(60_000)',
  ],
  ["spread overrides bubble timeout", "timeout: 5_000", "timeout: 5_000, ...{ timeout: 60_000 }"],
  ["duplicate overrides status timeout", "timeout: 10_000", "timeout: 10_000, timeout: 60_000"],
  [
    "receiver delay before content validation",
    "expect(created.content).toBe(message)",
    "await receiverPage.waitForTimeout(60_000)\n      expect(created.content).toBe(message)",
  ],
  [
    "receiver delay before JSON",
    "const created = (await messageResponse.json())",
    "await receiverPage.waitForTimeout(60_000)\n      const created = (await messageResponse.json())",
  ],
]) {
  test(`Enter sender contract rejects ${name}`, () => {
    const candidate = spec.replace(original, replacement)
    assert.ok(candidate !== spec)
    enterScenario(candidate)
    assert.throws(() => assertEnterSenderContract(candidate), { name: "AssertionError" })
  })
}

for (const location of ["row XPath", "status name"]) {
  test(`Enter sender contract rejects nested await in ${location}`, () => {
    const { body, print } = enterScenario(spec)
    const statement = [...body.statements].find((node) =>
      print(node).startsWith(
        location === "row XPath" ? "const senderRow =" : 'await expect(senderRow.getByRole("img",'
      )
    )
    const expression =
      location === "row XPath"
        ? statement.declarationList.declarations[0].initializer.arguments[0]
        : statement.expression.expression.expression.expression.arguments[0].arguments[1]
            .properties[0].initializer
    const original = spec.slice(expression.getStart(), expression.end)
    const replacement =
      location === "row XPath"
        ? `${original} + (await page.waitForTimeout(60_000), "")`
        : `(await page.waitForTimeout(60_000), ${original})`
    const candidate =
      spec.slice(0, expression.getStart()) + replacement + spec.slice(expression.end)
    enterScenario(candidate)
    assert.throws(() => assertEnterSenderContract(candidate), {
      name: "AssertionError",
      message:
        "only the response, JSON, visibility and status awaits are allowed in the critical window",
    })
  })
}

test("Enter sender contract rejects asynchronous iteration in the critical window", () => {
  const candidate = spec.replace(
    "expect(created.content).toBe(message)",
    "for await (const _ of [new Promise(resolve => setTimeout(resolve, 60_000))]) {}\n      expect(created.content).toBe(message)"
  )
  assert.ok(candidate !== spec)
  enterScenario(candidate)
  assert.throws(() => assertEnterSenderContract(candidate), {
    name: "AssertionError",
    message: "asynchronous iteration is forbidden in the critical window",
  })
})
