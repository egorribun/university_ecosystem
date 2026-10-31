import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { registerHooks } from "node:module"
import { fileURLToPath, pathToFileURL } from "node:url"

const frameFile = process.env.WS_BACKEND_FRAMES
assert.ok(frameFile, "WS_BACKEND_FRAMES must point to the current Python output")

// Node's native TypeScript loader needs the extension that Vite resolves.
registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier === "./messageLimits" && context.parentURL?.endsWith("/wsMessage.ts")) {
      return nextResolve("./messageLimits.ts", context)
    }
    return nextResolve(specifier, context)
  },
})

const schemaPath = fileURLToPath(new URL("../src/api/schemas/wsMessage.ts", import.meta.url))
const { parseWsMessage } = await import(pathToFileURL(schemaPath).href)
const frames = JSON.parse(await readFile(frameFile, "utf8"))
assert.equal(frames.length, 7, "all seven backend emitter cases must be present")

for (const frame of frames) {
  const parsed = parseWsMessage(JSON.stringify(frame))
  assert.notEqual(parsed, null, `backend frame ${frame.type} must be accepted`)
  assert.equal(parsed.type, frame.type)
  if ("chat_id" in frame) assert.equal(parsed.chat_id, frame.chat_id)
  if ("user_id" in frame) assert.equal(parsed.user_id, frame.user_id)
  if (frame.type === "new_message") {
    assert.equal(parsed.message.id, frame.message.id)
    assert.equal(parsed.message.content, frame.message.content)
  }
}

for (const [kind, field] of [
  ["typing", "user_name"],
  ["read", "read_at"],
  ["presence", "active"],
]) {
  const mutated = structuredClone(frames.find((frame) => frame.type === kind))
  delete mutated[field]
  assert.equal(parseWsMessage(JSON.stringify(mutated)), null, `${kind} must require ${field}`)
}

const mutatedMessage = structuredClone(frames.find((frame) => frame.type === "new_message"))
delete mutatedMessage.message.chat_id
assert.equal(parseWsMessage(JSON.stringify(mutatedMessage)), null)
process.stdout.write("7 backend frames accepted; 4 malformed controls rejected\n")
