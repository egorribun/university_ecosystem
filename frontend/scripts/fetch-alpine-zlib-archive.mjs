import { writeFile } from "node:fs/promises"
import https from "node:https"
import { pathToFileURL } from "node:url"

const archives = {
  x86_64: {
    url: "https://dl-cdn.alpinelinux.org/alpine/v3.24/releases/x86_64/alpine-virt-3.24.3-x86_64.iso",
    range: "bytes=15585280-15641489",
    contentRange: "bytes 15585280-15641489/70254592",
    size: 56210,
  },
  aarch64: {
    url: "https://dl-cdn.alpinelinux.org/alpine/v3.24/releases/aarch64/alpine-virt-3.24.3-aarch64.iso",
    range: "bytes=16148480-16202813",
    contentRange: "bytes 16148480-16202813/93452288",
    size: 54334,
  },
}

export async function fetchAlpineZlibArchive(arch) {
  if (!Object.hasOwn(archives, arch)) throw new Error("Unsupported Alpine architecture")
  const spec = archives[arch]
  return new Promise((resolve, reject) => {
    const body = Buffer.alloc(spec.size)
    let request
    let response
    let received = 0
    let settled = false
    const deadline = setTimeout(() => fail(new Error("Alpine archive request timed out")), 18000)

    function fail(error) {
      if (settled) return
      settled = true
      clearTimeout(deadline)
      response?.destroy()
      request?.destroy()
      reject(error)
    }

    try {
      request = https.get(
        spec.url,
        { headers: { Range: spec.range, "Accept-Encoding": "identity" }, maxHeaderSize: 8192 },
        (incoming) => {
          response = incoming
          incoming.on("error", fail)
          incoming.on("aborted", () => fail(new Error("Alpine archive response aborted")))
          incoming.on("close", () => {
            if (!incoming.complete) fail(new Error("Alpine archive response closed"))
          })
          const encoding = incoming.headers["content-encoding"]
          if (
            incoming.statusCode !== 206 ||
            incoming.headers["content-range"] !== spec.contentRange ||
            incoming.headers["content-length"] !== String(spec.size) ||
            (encoding !== undefined && encoding !== "identity")
          ) {
            fail(new Error("Invalid Alpine archive range response"))
            return
          }
          incoming.on("data", (chunk) => {
            if (settled) return
            if (!Buffer.isBuffer(chunk) || chunk.length > spec.size - received) {
              fail(new Error("Alpine archive response exceeded its range"))
              return
            }
            chunk.copy(body, received)
            received += chunk.length
          })
          incoming.on("end", () => {
            if (settled) return
            if (!incoming.complete || received !== spec.size) {
              fail(new Error("Alpine archive response was incomplete"))
              return
            }
            settled = true
            clearTimeout(deadline)
            resolve(body)
          })
        }
      )
      request.on("error", fail)
    } catch (error) {
      fail(error)
    }
  })
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    if (process.argv.length !== 3) throw new Error("Expected one architecture argument")
    await writeFile("/tmp/zlib.apk", await fetchAlpineZlibArchive(process.argv[2]), { mode: 0o600 })
  } catch {
    console.error("Unable to fetch the pinned Alpine archive")
    process.exitCode = 1
  }
}
