import { copyFile, readFile, writeFile } from "node:fs/promises"
import path from "node:path"
import process from "node:process"
import { pathToFileURL } from "node:url"

const LEGAL_FILES = [
  "LICENSE",
  "LICENSE-THIRD-PARTY",
  "LICENSE-THIRD-PARTY-SOURCES.md",
  "LICENSE-RUST-STD",
  "LICENSE-RUST-STD-COPYRIGHT.txt",
  "LICENSE-RUST-STD-SOURCES.md",
]

/** Retain every project, dependency and Rust runtime notice in npm archives. */
export async function finalizeWasmLicenses(frontendRoot) {
  for (const crate of ["rust-crypto", "wasm-sanitizer"]) {
    const source = path.join(frontendRoot, crate)
    const pkg = path.join(source, "pkg")
    const manifestPath = path.join(pkg, "package.json")
    const manifest = JSON.parse(await readFile(manifestPath, "utf8"))
    if (!Array.isArray(manifest.files))
      throw new Error(`${crate}: generated package files must be an array`)
    for (const file of LEGAL_FILES) {
      await copyFile(path.join(source, file), path.join(pkg, file))
      if (!manifest.files.includes(file)) manifest.files.push(file)
    }
    // wasm-pack inherits filesystem enumeration order for extra notices.
    // npm treats this list as a set; canonical order keeps producer bytes portable.
    manifest.files = [...new Set(manifest.files)].sort()
    await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8")
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  await finalizeWasmLicenses(process.cwd())
}
