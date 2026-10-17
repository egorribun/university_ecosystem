import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import { URL } from "node:url"
import ts from "typescript"

const hookPath = new URL("../../src/hooks/usePushPreferences.ts", import.meta.url)
const sectionPath = new URL(
  "../../src/pages/settings/sections/NotificationsSection.tsx",
  import.meta.url
)
const subscriptionPath = new URL("../../src/push/subscribe.ts", import.meta.url)

async function parseTypeScript(path) {
  const text = await readFile(path, "utf8")
  const source = ts.createSourceFile(
    path.pathname,
    text,
    ts.ScriptTarget.Latest,
    true,
    path.pathname.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS
  )
  return { source, text }
}

function walk(node, visit) {
  visit(node)
  ts.forEachChild(node, (child) => walk(child, visit))
}

function findVariable(root, name) {
  let result
  walk(root, (node) => {
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.name.text === name) {
      result = node
    }
  })
  return result
}

function findFunction(root, name) {
  let result
  walk(root, (node) => {
    if (ts.isFunctionDeclaration(node) && node.name?.text === name) result = node
  })
  return result
}

function unwrapCallback(initializer) {
  if (initializer && ts.isCallExpression(initializer)) {
    const [callback] = initializer.arguments
    if (callback && (ts.isArrowFunction(callback) || ts.isFunctionExpression(callback))) {
      return callback
    }
  }
  if (initializer && (ts.isArrowFunction(initializer) || ts.isFunctionExpression(initializer))) {
    return initializer
  }
  return undefined
}

function callExpressions(root) {
  const calls = []
  walk(root, (node) => {
    if (ts.isCallExpression(node)) calls.push(node)
  })
  return calls
}

function callName(call) {
  return call.expression.getText()
}

function hasCall(root, name) {
  return callExpressions(root).some((call) => callName(call) === name)
}

function findNode(root, predicate) {
  let result
  walk(root, (node) => {
    if (result === undefined && predicate(node)) result = node
  })
  return result
}

function namedHook(source) {
  const hook = findFunction(source, "usePushPreferences")
  assert.ok(hook, "the push preferences hook must remain discoverable")
  return hook
}

test("loading notification settings only reads the owned browser subscription", async () => {
  const { source } = await parseTypeScript(hookPath)
  const hook = namedHook(source)
  const detector = findVariable(hook, "detectSubscription")
  assert.ok(detector, "the mount-time subscription detector must remain explicit")
  const detectorBody = unwrapCallback(detector.initializer)
  assert.ok(detectorBody, "the mount-time detector must be a callable callback")

  assert.ok(
    hasCall(detectorBody, "getOwnedPushSubscription"),
    "mount may read a subscription already owned by this account"
  )
  for (const forbiddenCall of [
    "Notification.requestPermission",
    "ensurePushSubscription",
    "PushManager.subscribe",
    "pushManager.subscribe",
    "subscribePush",
  ]) {
    assert.equal(
      hasCall(detectorBody, forbiddenCall),
      false,
      `mount must not call ${forbiddenCall}; push opt-in requires user action`
    )
  }
})

test("the explicit notifications switch owns permission and subscription requests", async () => {
  const [{ source: hookSource }, { source: sectionSource }] = await Promise.all([
    parseTypeScript(hookPath),
    parseTypeScript(sectionPath),
  ])
  const hook = namedHook(hookSource)
  const enableDeclaration = findVariable(hook, "enableNotifications")
  assert.ok(enableDeclaration, "the opt-in action must remain a named callback")
  const enableCallback = unwrapCallback(enableDeclaration.initializer)
  assert.ok(enableCallback, "the opt-in callback must be callable")

  const enableCalls = callExpressions(enableCallback)
  const permissionCall = enableCalls.find(
    (call) => callName(call) === "Notification.requestPermission"
  )
  const subscriptionCall = enableCalls.find((call) => callName(call) === "ensurePushSubscription")
  assert.ok(permissionCall, "explicit opt-in must request notification permission when needed")
  assert.ok(subscriptionCall, "explicit opt-in must create or bind the browser subscription")
  assert.ok(
    permissionCall.pos < subscriptionCall.pos,
    "permission must be resolved before subscription is ensured"
  )
  assert.match(
    subscriptionCall.getText(),
    /requestPermission\s*:\s*false/u,
    "the subscription helper must not issue a second permission prompt"
  )

  const section = findFunction(sectionSource, "NotificationsSection")
  assert.ok(section, "the settings section must remain a named component")
  const toggle = findVariable(section, "handleNotificationsToggle")
  assert.ok(toggle, "the opt-in callback must be connected to the explicit switch handler")
  const toggleCallback = unwrapCallback(toggle.initializer)
  assert.ok(toggleCallback, "the notification switch handler must be callable")
  assert.ok(
    callExpressions(toggleCallback).some((call) => callName(call) === "enableNotifications"),
    "checking the switch must enter the explicit opt-in action"
  )
  assert.match(
    toggleCallback.getText(),
    /if\s*\(checked\)[\s\S]*enableNotifications\(\)/u,
    "subscription is enabled only on the checked switch action"
  )

  let switchUsesToggle = false
  walk(section, (node) => {
    if (
      ts.isJsxAttribute(node) &&
      node.name.getText() === "onChange" &&
      node.initializer &&
      ts.isJsxExpression(node.initializer) &&
      node.initializer.expression?.getText() === "handleNotificationsToggle"
    ) {
      switchUsesToggle = true
    }
  })
  assert.equal(switchUsesToggle, true, "the visible switch must use the explicit opt-in handler")
})

test("startup sync requires prior account ownership and an existing browser subscription", async () => {
  const { source } = await parseTypeScript(subscriptionPath)
  const sync = findFunction(source, "syncPushForConfirmedIdentity")
  assert.ok(sync?.body, "the startup sync policy must remain explicit")

  const ownerGuard = findNode(
    sync.body,
    (node) =>
      ts.isIfStatement(node) &&
      node.expression.getText().includes("browserOwner !== owner") &&
      node.thenStatement.getText().includes("return null")
  )
  assert.ok(ownerGuard, "a new account must stop before automatic subscription sync")
  const syncCalls = callExpressions(sync.body)
  const recoveryCall = syncCalls.find((call) => callName(call) === "recoverPushConsentFromBrowser")
  const softSyncCall = syncCalls.find((call) => callName(call) === "softSyncPushSubscription")
  assert.ok(recoveryCall && softSyncCall, "owned previous consent may be recovered and rebound")
  assert.ok(ownerGuard.end < recoveryCall.pos, "ownership must be checked before consent recovery")
  assert.ok(ownerGuard.end < softSyncCall.pos, "ownership must be checked before any auto-sync")

  const recovery = findFunction(source, "recoverPushConsentFromBrowser")
  assert.ok(recovery?.body, "browser consent recovery must remain explicit")
  const subscriptionGuard = findNode(
    recovery.body,
    (node) =>
      ts.isIfStatement(node) &&
      node.expression.getText().includes("reg.pushManager.getSubscription") &&
      node.thenStatement.getText().includes("return false")
  )
  const ensureCall = callExpressions(recovery.body).find(
    (call) => callName(call) === "ensurePushSubscription"
  )
  assert.ok(subscriptionGuard && ensureCall, "recovery must verify browser state before rebinding")
  assert.ok(
    subscriptionGuard.end < ensureCall.pos,
    "startup recovery may rebind a pre-existing subscription, not create the first one"
  )
})
