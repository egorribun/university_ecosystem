import { configureAxe } from "jest-axe"

const axe = configureAxe({
  rules: {
    "document-title": { enabled: false },
    "html-has-lang": { enabled: false },
    "landmark-one-main": { enabled: false },
  },
})

type AxeRunOptions = Parameters<typeof axe>[1]

export async function checkA11y(container: HTMLElement, options?: AxeRunOptions) {
  const results = await axe(container, options)
  expect(results).toHaveNoViolations()
  return results
}
