import { preview } from "vite"
import path from "node:path"
import process from "node:process"
import { fileURLToPath } from "node:url"

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const frontendRoot = path.resolve(__dirname, "..")

const DEFAULT_PORT = 4174
const host = process.env.LHCI_PREVIEW_HOST ?? process.env.HOST ?? "127.0.0.1"
const port = Number.parseInt(
  process.env.LHCI_PREVIEW_PORT ?? process.env.PORT ?? String(DEFAULT_PORT),
  10
)

if (Number.isNaN(port)) {
  console.error("Invalid port provided for Lighthouse preview")
  process.exitCode = 1
  process.exit()
}

const strictPort = (process.env.LHCI_STRICT_PORT ?? "true").toLowerCase() !== "false"

async function main() {
  const server = await preview({
    root: frontendRoot,
    preview: {
      host,
      port,
      strictPort,
    },
  })

  const close = async () => {
    await server.close()
    process.exit(0)
  }

  process.on("SIGTERM", close)
  process.on("SIGINT", close)

  server.printUrls()
  console.log(`LHCI_READY http://${host}:${port}/`)
  process.stdin.resume()
}

main().catch((error) => {
  console.error("Failed to start Lighthouse preview server", error)
  process.exitCode = 1
})
