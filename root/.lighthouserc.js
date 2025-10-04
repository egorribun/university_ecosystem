import { ci as frontendCi } from "./frontend/.lighthouserc.js"

const config = { ci: frontendCi }

export const ci = config.ci
export default config
