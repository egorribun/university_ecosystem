/* global console, process */
import fs from "fs"
import path from "path"
import { fileURLToPath } from "url"
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

// 2. Test battery (25 test cases)
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

// 3. Invariants every sanitization mode must uphold for every input.
const dangerousPatterns = [
  { label: "script element", pattern: /<\s*\/?\s*script/i },
  { label: "javascript: protocol", pattern: /javascript\s*:/i },
  { label: "data:text/html URL", pattern: /data\s*:\s*text\/html/i },
  { label: "inline event handler", pattern: /<[^>]*\son[a-z]+\s*=/i },
  { label: "style attribute", pattern: /<[^>]*\sstyle\s*=/i },
  { label: "class or id attribute", pattern: /<[^>]*\s(?:class|id)\s*=/i },
  { label: "img element", pattern: /<\s*img\b/i },
]

const modes = [
  { name: "RICH_TEXT", run: sanitize_rich_text },
  { name: "BASIC", run: sanitize_html_basic },
  { name: "STRIP", run: strip_html },
]

console.log("Starting WASM Sanitizer Safety Invariant Tests...\n")

let failedCount = 0

for (const tc of testCases) {
  console.log(`Testing Case: "${tc.name}"`)

  for (const mode of modes) {
    const output = mode.run(tc.input)

    for (const { label, pattern } of dangerousPatterns) {
      if (pattern.test(output)) {
        console.error(`  FAIL [${mode.name}] output contains ${label}!`)
        console.error(`    Input:  "${tc.input}"`)
        console.error(`    Output: "${output}"`)
        failedCount++
      }
    }

    // STRIP removes every tag, so no markup may survive at all.
    if (mode.name === "STRIP" && /<\s*\/?\s*[a-z]/i.test(output)) {
      console.error(`  FAIL [STRIP] output still contains markup!`)
      console.error(`    Input:  "${tc.input}"`)
      console.error(`    Output: "${output}"`)
      failedCount++
    }

    // The sanitizer must be deterministic for the same input.
    if (mode.run(tc.input) !== output) {
      console.error(`  FAIL [${mode.name}] output is not deterministic!`)
      failedCount++
    }
  }
}

// Plain text and Unicode content must survive every mode unchanged.
for (const text of ["Hello world, no HTML tags.", "Hello Emojis 🚀 🌟 👋 🌍 🎉"]) {
  for (const mode of modes) {
    if (mode.run(text) !== text) {
      console.error(`  FAIL [${mode.name}] altered plain text "${text}"`)
      failedCount++
    }
  }
}

if (failedCount > 0) {
  console.error(`\nTest suite FAILED: ${failedCount} invariant violations detected.`)
  process.exit(1)
} else {
  console.log(
    `\nAll ${testCases.length} test cases PASSED successfully in all 3 sanitization modes!`
  )
  process.exit(0)
}
