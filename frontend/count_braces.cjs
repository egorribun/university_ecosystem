const fs = require("fs")

function countBraces(file) {
  const content = fs.readFileSync(file, "utf8")
  let open = 0
  let close = 0
  for (let char of content) {
    if (char === "{") open++
    if (char === "}") close++
  }
  console.log(`${file}: Open=${open}, Close=${close}, Diff=${open - close}`)
}

countBraces(process.argv[2])
