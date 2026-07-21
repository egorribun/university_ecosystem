# WASM Release Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent the frontend from accepting, building with, or shipping fake
WASM sanitizer and cryptography packages.

**Architecture:** A Node validator is the shared trust boundary for both local
development and CI. It validates wasm-pack package shape, actual WebAssembly
bytes and required JavaScript exports. The orchestrated build runs wasm-pack
then the validator and propagates any error; runtime smoke tests initialize
the generated binaries and prove sanitizer/crypto behaviour.

**Tech Stack:** Node 22+, Node test runner, wasm-pack 0.13.1, wasm-bindgen,
Rust 2021 crates, Vite 8 and Vitest 3.

## Global Constraints

- Never use JavaScript cryptography or sanitizer fallbacks as successful WASM
  output.
- A missing or invalid artifact fails the command with a non-zero exit status.
- Both `*_bg.wasm` files must begin with `00 61 73 6d`, be accepted by
  `WebAssembly.validate`, and be larger than 32 bytes.
- The sanitizer must remove executable markup; PBKDF2, scrypt and HMAC must
  match deterministic known-answer values.
- Generated packages are checked in only when produced by `wasm-pack build
  --target web`; mock data and no-op exports are forbidden.

---

### Task 1: Make artifact validity a tested interface

**Files:**
- Create: `frontend/scripts/verify-wasm-artifacts.mjs`
- Create: `frontend/scripts/verify-wasm-artifacts.test.mjs`
- Modify: `frontend/package.json`

**Interfaces:**
- Produces `validateWasmArtifacts(root: string): Promise<void>`.
- Produces CLI exit code `0` only when both packages pass validation.
- Adds `test:wasm-artifacts` as `node --test scripts/verify-wasm-artifacts.test.mjs`.

- [ ] **Step 1: Write the failing validator tests**

```js
test("rejects text masquerading as a WebAssembly module", async () => {
  await writeFixture("wasm-sanitizer/pkg/wasm_sanitizer_bg.wasm", "mock_wasm_data\\n")
  await assert.rejects(() => validateWasmArtifacts(fixtureRoot), /valid WebAssembly module/)
})

test("rejects a module with missing generated exports", async () => {
  await writeValidWasm("wasm-sanitizer/pkg/wasm_sanitizer_bg.wasm")
  await writeFixture("wasm-sanitizer/pkg/wasm_sanitizer.js", "export default async function init() {}")
  await assert.rejects(() => validateWasmArtifacts(fixtureRoot), /sanitize_rich_text/)
})
```

- [ ] **Step 2: Run the tests and observe RED**

Run: `node --test scripts/verify-wasm-artifacts.test.mjs`

Expected: failure because the validator module does not exist.

- [ ] **Step 3: Implement the minimal validator**

```js
const WASM_MAGIC = Buffer.from([0x00, 0x61, 0x73, 0x6d])

function assertValidWasm(bytes, label) {
  if (bytes.length <= 32 || !bytes.subarray(0, 4).equals(WASM_MAGIC) || !WebAssembly.validate(bytes)) {
    throw new Error(`${label} is not a valid WebAssembly module`)
  }
}
```

Validate `package.json`, JavaScript glue and `.wasm` for both packages, and
reject exact mock sentinels and no-op function bodies before exporting the
function and invoking it from the CLI.

- [ ] **Step 4: Run GREEN and the command-line validator**

Run: `node --test scripts/verify-wasm-artifacts.test.mjs`

Expected: all validator tests pass.

Run: `node scripts/verify-wasm-artifacts.mjs`

Expected before Task 3: non-zero exit with a malformed artifact error.

### Task 2: Fail the frontend build closed

**Files:**
- Modify: `frontend/scripts/build-orchestrated.mjs`
- Modify: `frontend/scripts/ensure-wasm.mjs`
- Test: `frontend/scripts/verify-wasm-artifacts.test.mjs`

**Interfaces:**
- Consumes `validateWasmArtifacts` from Task 1.
- Produces a build which rejects any wasm-pack/validation failure.

- [ ] **Step 1: Add the failing orchestration assertion**

```js
test("the orchestrated build does not convert a wasm-pack failure into success", async () => {
  const result = await runBuildWithMissingWasmPack()
  assert.notStrictEqual(result.exitCode, 0)
  assert.match(result.stderr, /wasm-pack|WebAssembly/i)
})
```

- [ ] **Step 2: Run RED**

Run: `node --test scripts/verify-wasm-artifacts.test.mjs`

Expected: failure because the existing build catches and suppresses the error.

- [ ] **Step 3: Propagate failures**

Replace the `try/catch` in `step1_wasm()` with sequential `await run(...)`
calls, then invoke `node ./scripts/verify-wasm-artifacts.mjs`. Change
`ensure-wasm.mjs` to call the same validator and `process.exitCode = 1` when
the package is absent or invalid.

- [ ] **Step 4: Run GREEN**

Run: `node --test scripts/verify-wasm-artifacts.test.mjs`

Expected: the simulated missing tool and malformed package both fail closed.

### Task 3: Generate and verify authentic packages

**Files:**
- Modify: `frontend/wasm-sanitizer/pkg/*` (wasm-pack generated output only)
- Modify: `frontend/rust-crypto/pkg/*` (wasm-pack generated output only)
- Create: `frontend/scripts/wasm-runtime-smoke.test.mjs`

**Interfaces:**
- Initializes both generated modules from their corresponding `*_bg.wasm`.
- Produces real sanitizer and known-answer cryptographic results.

- [ ] **Step 1: Write failing runtime smoke tests**

```js
assert.doesNotMatch(sanitize_rich_text('<img src=x onerror=alert(1)><script>x</script>'), /onerror|<script/i)
assert.equal(pbkdf2_derive('password', 'salt', 1, 32), '120fb6cffcf8b32c43e7225256c4f837a86548c92ccc35480805987cb70be17b')
assert.equal(hmac_sha256_sign('key', 'The quick brown fox jumps over the lazy dog'), 'f7bc83f430538424b13298e6aa6fb143ef4d59a14946175997479dbc2d1a3cd8')
assert.equal(scrypt_derive('password', 'NaCl', 1024, 8, 16, 64).length, 64)
```

- [ ] **Step 2: Run RED against the current packages**

Run: `node --test scripts/wasm-runtime-smoke.test.mjs`

Expected: sanitizer and cryptographic assertions fail against the placeholders.

- [ ] **Step 3: Build only with wasm-pack**

Run from `frontend/`: `wasm-pack build wasm-sanitizer --target web --release`

Run from `frontend/`: `wasm-pack build rust-crypto --target web --release`

Do not edit the generated files manually. Inspect the generated `.wasm` magic,
run `node scripts/verify-wasm-artifacts.mjs`, then stage only wasm-pack output.

- [ ] **Step 4: Run GREEN**

Run: `node --test scripts/wasm-runtime-smoke.test.mjs`

Expected: all vectors pass using initialized generated modules.

### Task 4: Preserve the Rust error contract and remove coverage-only proof

**Files:**
- Modify: `frontend/rust-crypto/src/lib.rs`
- Modify: `native/rust_ext/src/lib.rs`
- Test: `frontend/rust-crypto/src/lib.rs` native unit tests
- Test: `native/rust_ext/src/lib.rs` native unit tests

**Interfaces:**
- `scrypt_derive` returns a caller-visible error for invalid output parameters;
  it never panics through the WASM/FFI boundary.
- PyO3 binding test asserts the concrete optimal-slot result, not a tautology.

- [ ] **Step 1: Add failing error and result assertions**

```rust
assert!(scrypt_derive(b"p", b"s", 1024, 8, 1, 1).is_err());
assert_eq!(opt_item.expect("available slot").start_time, 3_600);
```

- [ ] **Step 2: Run RED**

Run: `cargo test --lib scrypt_invalid_output_returns_error`

Expected: failure because the existing `expect` panics or the slot assertion is
not expressed.

- [ ] **Step 3: Restore error mapping and behavioural assertion**

Map `scrypt(...)` errors through `make_err`, and choose fixture availability
that deterministically yields the asserted start time.

- [ ] **Step 4: Run GREEN**

Run: `cargo test --no-default-features --lib` in `native/rust_ext/`.

Run: `cargo test --lib` in `frontend/rust-crypto/`.

### Task 5: Verify release behaviour and document evidence

**Files:**
- Modify: `docs/testing/roadmap-100-percent-quality.md` only with fresh
  evidence for the completed P0 sub-items.

- [ ] **Step 1: Run the focused release-safety gate**

Run from `frontend/`:

```text
node --test scripts/verify-wasm-artifacts.test.mjs scripts/wasm-runtime-smoke.test.mjs
node scripts/verify-wasm-artifacts.mjs
npm run typecheck
npm run test:ci
npm run build
```

- [ ] **Step 2: Run the Rust checks**

Run:

```text
cargo fmt --all -- --check
cargo test --no-default-features --lib
cargo test --lib
wasm-pack test --headless --chrome frontend/rust-crypto
```

- [ ] **Step 3: Record only proven results**

Add command, platform, timestamp and artifact paths beside the related
roadmap item. Do not mark any larger wave complete from this P0 work.
