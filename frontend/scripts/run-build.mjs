import { spawn } from "node:child_process"
import path from "node:path"
import process from "node:process"

const args = process.argv.slice(2)
const wantsReport = args.includes("--report")
const sanitizedArgs = args.filter((arg) => arg !== "--report")

const env = {
  ...process.env,
  ...(wantsReport ? { BUILD_REPORT: "1", ANALYZE: process.env.ANALYZE ?? "1" } : {}),
}

function run(command, commandArgs, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, commandArgs, { stdio: "inherit", env, ...options })
    child.on("error", (err) => {
      console.error("Failed to start %s:", command, err)
      reject(err)
    })
    child.on("close", (code) => {
      if (code !== 0) {
        console.error(`${command} exited with code ${code}`)
        reject(new Error(`${command} exited with code ${code}`))
      } else {
        resolve(undefined)
      }
    })
  })
}

async function main() {
  console.log("Building rust-crypto WASM...")
  try {
    await run("wasm-pack", ["build", "rust-crypto", "--target", "web"], {
      cwd: path.resolve(process.cwd()),
      shell: true,
    })
    await run("wasm-pack", ["build", "wasm-sanitizer", "--target", "web"], {
      cwd: path.resolve(process.cwd()),
      shell: true,
    })
  } catch (error) {
    console.warn(
      "WASM build failed. If this is a non-rust environment, ensure rust-crypto/pkg and wasm-sanitizer/pkg exist."
    )
    console.warn(error.message)
  }

  console.log("Syncing tokens...")
  await run("node", ["./scripts/sync-tokens.mjs"])

  await run("vite", ["build", ...sanitizedArgs], {
    cwd: path.resolve(process.cwd()),
    shell: true,
  })
  if (wantsReport) {
    await run("node", [path.resolve(process.cwd(), "scripts/check-bundle-budget.mjs")])
  }

  // Wave 125 Phase 2 — post-build HTML processing (font preload, CSP
  // nonce placeholder, VITE_LHCI placeholder replacement, mirror
  // `_shell.html` → `index.html` for static-serve compat) is delegated
  // to a sibling script spawned as a fresh node child process. Two
  // alternative approaches turned out unreliable:
  //   - npm pre/post lifecycle hooks (`postbuild`) are not auto-run by
  //     `npm run build` since npm 7+ (only for install/version etc).
  //   - In-process `await postBuildShellProcess()` from inside this
  //     `main()` was sometimes skipped on Windows after vite's child
  //     process exited under shell:true (parent event loop shutdown).
  // Spawning a fresh `node` child as the last step gives us
  // deterministic execution + clear log separation.
  await run("node", [path.resolve(process.cwd(), "scripts/post-build-shell.mjs")])
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
