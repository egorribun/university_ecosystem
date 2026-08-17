import sharp from "sharp"
import { fileURLToPath } from "url"
import { dirname, join } from "path"
import { existsSync } from "fs"

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)
const publicDir = join(__dirname, "../public")
const sourceImage = join(publicDir, "guu_logo.png")

if (!existsSync(sourceImage)) {
  console.error("Source image guu_logo.png not found in public directory!")
  process.exit(1)
}

const targets = [
  { name: "favicon-16x16.png", size: 16 },
  { name: "favicon-32x32.png", size: 32 },
  { name: "apple-touch-icon.png", size: 180 },
  { name: "icon-192.png", size: 192 },
  { name: "icon-512.png", size: 512 },
]

async function generateIcons() {
  console.log("Generating icons from guu_logo.png...")

  for (const target of targets) {
    const filePath = join(publicDir, target.name)
    try {
      // 1. Trim transparent pixels
      // 2. Resize to 80% of target size (20% padding)
      const paddingRatio = 0.2 // 10% on each side
      const innerSize = Math.floor(target.size * (1 - paddingRatio)) || 1

      const resizedBuffer = await sharp(sourceImage)
        .trim()
        .resize({
          width: innerSize,
          height: innerSize,
          fit: "contain",
          background: { r: 0, g: 0, b: 0, alpha: 0 },
        })
        .toBuffer()

      // 3. Composite onto a transparent canvas of target.size
      await sharp({
        create: {
          width: target.size,
          height: target.size,
          channels: 4,
          background: { r: 0, g: 0, b: 0, alpha: 0 },
        },
      })
        .composite([{ input: resizedBuffer }])
        .toFile(filePath)

      console.log(`Created ${target.name}`)
    } catch (err) {
      console.error("Error creating %s:", target.name, err)
    }
  }

  // Handle favicon.ico separately
  const icoPath = join(publicDir, "favicon.ico")
  try {
    const innerSize = Math.floor(32 * 0.8)
    const resized = await sharp(sourceImage)
      .trim()
      .resize({
        width: innerSize,
        height: innerSize,
        fit: "contain",
        background: { r: 0, g: 0, b: 0, alpha: 0 },
      })
      .toBuffer()

    await sharp({
      create: {
        width: 32,
        height: 32,
        channels: 4,
        background: { r: 0, g: 0, b: 0, alpha: 0 },
      },
    })
      .composite([{ input: resized }])
      .toFormat("png")
      .toFile(icoPath)

    console.log(`Created favicon.ico`)
  } catch (err) {
    console.error("Error creating favicon.ico", err)
  }
}

generateIcons()
