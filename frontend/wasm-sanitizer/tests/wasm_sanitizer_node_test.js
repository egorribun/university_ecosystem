/* eslint-env node */
import fs from "fs"
import path from "path"
import { fileURLToPath } from "url"
import { spawnSync } from "child_process"
import {
  initSync,
  sanitize_rich_text,
  sanitize_html_basic,
  strip_html,
} from "../pkg/wasm_sanitizer.js"

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

// 1. Initialize WASM module
const wasmPath = path.resolve(__dirname, "../pkg/wasm_sanitizer_bg.wasm")
const wasmBuffer = fs.readFileSync(wasmPath)
initSync(wasmBuffer)

// 2. Python helper for pyo3-sanitizer output
function pythonSanitize(input, mode) {
  const pyCode = `
import sys
import pyo3_sanitizer
input_str = sys.stdin.read()
if sys.argv[1] == 'rich':
    sys.stdout.write(pyo3_sanitizer.sanitize_rich_text(input_str))
elif sys.argv[1] == 'basic':
    sys.stdout.write(pyo3_sanitizer.sanitize_html_basic(input_str))
elif sys.argv[1] == 'strip':
    sys.stdout.write(pyo3_sanitizer.strip_html(input_str))
`
  const res = spawnSync("uv", ["run", "python", "-c", pyCode, mode], {
    input: input,
    encoding: "utf8",
  })
  if (res.error) {
    throw res.error
  }
  if (res.status !== 0) {
    throw new Error(`Python execution failed: ${res.stderr}`)
  }
  return res.stdout
}

// 3. Test battery (25 test cases)
const testCases = [
  { name: "empty string", input: "" },
  { name: "plain text", input: "Hello world, no HTML tags." },
  {
    name: "basic rich text tags",
    input: "<p>Hello <b>world</b></p><ul><li>item 1</li><li>item 2</li></ul>",
  },
  {
    name: "allowed headings and code",
    input: "<h1>Title</h1><h3>Subtitle</h3><pre><code>let x = 42;</code></pre>",
  },
  {
    name: "unallowed tags (div, span, img)",
    input: '<div class="evil"><span id="s1">nested text</span><img src="x" /></div>',
  },
  { name: "script tag XSS", input: "<script>alert(1)</script>" },
  {
    name: "script tag with attributes",
    input: '<script type="text/javascript" src="evil.js"></script>',
  },
  {
    name: "event handler attributes",
    input: '<a href="#" onclick="runEvil()">click me</a><b onerror="alert(1)">bold</b>',
  },
  { name: "javascript protocol href", input: '<a href="javascript:alert(1)">javascript link</a>' },
  {
    name: "data protocol href",
    input: '<a href="data:text/html,<script>alert(1)</script>">data link</a>',
  },
  {
    name: "safe https href and rel",
    input: '<a href="https://google.com" target="_blank" title="Google">Safe Link</a>',
  },
  { name: "style attribute", input: '<p style="color: red; background: blue;">styled text</p>' },
  { name: "Cyrillic Unicode", input: "<p>Привет, мир! <b>Как дела?</b></p>" },
  { name: "Japanese Unicode", input: "<span>こんにちは、世界！</span>" },
  { name: "Emojis preservation", input: "Hello Emojis 🚀 🌟 👋 🌍 🎉" },
  {
    name: "Deep tag nesting (150 levels)",
    input: "<div>".repeat(150) + "content" + "</div>".repeat(150),
  },
  { name: "Malformed HTML tags", input: '<p class="unclosed' },
  { name: "Special characters", input: "Text & symbols < > \" ' &amp;" },
  {
    name: "Disallowed attributes on allowed tags",
    input: '<p class="class1" id="p1" style="font-size: 12px;">paragraph</p>',
  },
  { name: "Mixed case script tag", input: "<ScRiPt>alert(1)</sCrIpT>" },
  { name: "Whitespace/tab protocol evasion", input: '<a href="  javascript:alert(1) ">link</a>' },
  { name: "Blockquote and pre", input: "<blockquote>Quote here</blockquote><pre>Pre text</pre>" },
  { name: "Newline evasion", input: '<a\nhref="javascript:alert(1)">link</a>' },
  {
    name: "Only inline basic elements",
    input: "<b>bold</b> and <i>italic</i> and <strong>strong</strong>",
  },
  {
    name: "Basic mode stripping rich elements",
    input: '<h1>Header</h1><a href="https://example.com">link</a>',
  },
]

console.log("Starting WASM vs PyO3 Sanitizer Iso-functional Parity Tests...\n")

let failedCount = 0

for (const tc of testCases) {
  console.log(`Testing Case: "${tc.name}"`)

  // Test RICH_TEXT mode
  const wasmRich = sanitize_rich_text(tc.input)
  const pyRich = pythonSanitize(tc.input, "rich")
  if (wasmRich !== pyRich) {
    console.error(`  FAIL [RICH_TEXT] parity mismatch!`)
    console.error(`    WASM:   "${wasmRich}"`)
    console.error(`    Python: "${pyRich}"`)
    failedCount++
  }

  // Test BASIC mode
  const wasmBasic = sanitize_html_basic(tc.input)
  const pyBasic = pythonSanitize(tc.input, "basic")
  if (wasmBasic !== pyBasic) {
    console.error(`  FAIL [BASIC] parity mismatch!`)
    console.error(`    WASM:   "${wasmBasic}"`)
    console.error(`    Python: "${pyBasic}"`)
    failedCount++
  }

  // Test STRIP mode
  const wasmStrip = strip_html(tc.input)
  const pyStrip = pythonSanitize(tc.input, "strip")
  if (wasmStrip !== pyStrip) {
    console.error(`  FAIL [STRIP] parity mismatch!`)
    console.error(`    WASM:   "${wasmStrip}"`)
    console.error(`    Python: "${pyStrip}"`)
    failedCount++
  }
}

if (failedCount > 0) {
  console.error(`\nTest suite FAILED: ${failedCount} mismatches detected.`)
  process.exit(1)
} else {
  console.log("\nAll 25 test cases PASSED successfully in all 3 sanitization modes!")
  process.exit(0)
}
