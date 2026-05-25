const fs = require("fs")
const path = "c:/Users/egorribun/Documents/university_ecosystem/frontend/src/pages/Settings.tsx"
let content = fs.readFileSync(path, "utf8")

// Replace setSnack with setSnackbar
content = content.replace(/setSnack\(/g, "setSnackbar(")
// Replace sev: with severity:
content = content.replace(/sev:/g, "severity:")
// Replace snack. with snackbar.
content = content.replace(/snack\.(?!text)/g, "snackbar.")
// Replace !!snack with !!snackbar
content = content.replace(/!!snack/g, "!!snackbar")
// Replace snack? with snackbar?
content = content.replace(/snack\?/g, "snackbar?")
// Fix the specific snackMessage rename in Profile if I were doing it here,
// but this is Settings.tsx.

fs.writeFileSync(path, content)
console.log("Done cleaning Settings.tsx")
