// Governed Stryker ignore policy (ADR-040).
//
// Only presentation-only string leaves are ignored: the Tailwind class lists
// and literal inline style values that decide how an element looks, never
// whether it behaves. Conditions, operators, calls, object shapes and every
// value that references program state stay mutated, so a styling *decision*
// (an active tab, a reduced-motion switch) still needs a killing test.

export const PRESENTATION_IGNORER = "presentation-class-names"
export const PRESENTATION_IGNORE_REASON =
  "Presentation-only class or literal style value; governed by ADR-040"

const CLASS_HELPERS = new Set(["cn", "clsx", "cva", "twMerge", "twJoin"])
const CLASS_ATTRIBUTE = /^(?:className|[a-z][A-Za-z0-9]*ClassName)$/u
const CLASS_BINDING = /(?:^c|C)lass(?:es|Name|Names)$/u

const isLiteralLeaf = (node) =>
  node.type === "StringLiteral" ||
  (node.type === "TemplateLiteral" && node.expressions.length === 0)

const attributeName = (node) =>
  node.type === "JSXAttribute" && node.name.type === "JSXIdentifier" ? node.name.name : undefined

/** Is `child` a value position (not a test, key or callee) of `parent`? */
function isValuePosition(parent, child) {
  switch (parent.type) {
    case "ConditionalExpression":
      return parent.consequent === child || parent.alternate === child
    case "LogicalExpression":
    case "ArrayExpression":
    case "TemplateLiteral":
    case "JSXExpressionContainer":
    case "ObjectExpression":
      return true
    case "ObjectProperty":
      return parent.value === child
    default:
      return false
  }
}

/** Walk from a literal leaf to the construct that owns it. */
function presentationContext(path) {
  let child = path.node
  let parentPath = path.parentPath
  let insideStyleObject = false
  while (parentPath) {
    const parent = parentPath.node
    const name = attributeName(parent)
    if (name !== undefined) {
      if (CLASS_ATTRIBUTE.test(name)) return "class-attribute"
      if (name === "style" && insideStyleObject) return "style-attribute"
      return undefined
    }
    if (
      parent.type === "CallExpression" &&
      parent.callee.type === "Identifier" &&
      CLASS_HELPERS.has(parent.callee.name) &&
      parent.arguments.includes(child)
    ) {
      return "class-helper"
    }
    if (
      parent.type === "VariableDeclarator" &&
      parent.init === child &&
      parent.id.type === "Identifier" &&
      CLASS_BINDING.test(parent.id.name)
    ) {
      return "class-binding"
    }
    if (!isValuePosition(parent, child)) return undefined
    if (parent.type === "ObjectExpression") insideStyleObject = true
    child = parent
    parentPath = parentPath.parentPath
  }
  return undefined
}

export const presentationIgnorer = Object.freeze({
  shouldIgnore(path) {
    if (!isLiteralLeaf(path.node)) return undefined
    return presentationContext(path) === undefined ? undefined : PRESENTATION_IGNORE_REASON
  },
})

// Same shape as @stryker-mutator/api's declareValuePlugin(PluginKind.Ignore, …).
export const strykerPlugins = [
  { kind: "Ignore", name: PRESENTATION_IGNORER, value: presentationIgnorer },
]

/** The serializable instrumenter configuration every evidence stage agrees on. */
export const canonicalInstrumenterConfig = Object.freeze({
  plugins: null,
  excludedMutations: Object.freeze([]),
  ignorers: Object.freeze([PRESENTATION_IGNORER]),
})

/** Resolve the serializable configuration into Instrumenter options. */
export function resolveInstrumenterOptions(config = canonicalInstrumenterConfig) {
  if (JSON.stringify(config) !== JSON.stringify(canonicalInstrumenterConfig)) {
    throw new Error("Instrumenter configuration differs from the governed ignore policy")
  }
  return { plugins: null, excludedMutations: [], ignorers: [presentationIgnorer] }
}

/** An Ignored mutant is acceptable only when this policy produced it. */
export const isGovernedIgnoredMutant = (mutant) =>
  mutant?.status === "Ignored" && mutant.statusReason === PRESENTATION_IGNORE_REASON
