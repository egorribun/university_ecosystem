import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { NewsDetailBody } from "./NewsDetailBody"

// Wave 197 SW1 — NewsDetailBody Storybook fixture (CONTEXT-tier, cheap/ambient).
//
// Renders an article body from a single `content` prop: marked (isolated
// instance) → sanitizeArticleHtml (WASM ammonia, regex fallback in Storybook when
// the wasm pkg isn't built — RZ-24-04 pattern), with an auto Table of Contents
// (shown when ≥3 headings on desktop via useMediaQuery) and a legacy plain-text
// path for non-Markdown content. No callbacks; no theme scope beyond globals.
//
// Variants: WithToc (markdown, ≥3 headings → ToC) / Markdown (short, no ToC) /
// PlainText (legacy renderer: paragraphs + > pull-quotes).

const MARKDOWN_TOC = `## Background

The university has opened a new interdisciplinary lab spanning **data science**, robotics, and computational biology.

## Facilities

The space includes:

- A high-performance compute cluster
- Wet-lab benches for biology teams
- A collaborative robotics floor

## Research Tracks

Teams will pursue three initial tracks, with applications opening next term.

## Timeline

> The lab opens to graduate researchers in autumn, with undergraduate access following in spring.
`

const MARKDOWN_SHORT = `## Overview

A concise update with **bold** emphasis and a single heading — not enough headings to surface the table of contents.
`

const PLAIN_TEXT = `The new facility represents the largest single investment in cross-disciplinary research the campus has made in a decade.

> It is not about one field — it is about what happens at the seams between them.

Teams from across the university will share the space, the instruments, and the data.
`

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div className="news-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div style={{ maxWidth: 880, margin: "0 auto" }}>
          <Story />
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof NewsDetailBody> = {
  title: "News/NewsDetailBody",
  component: NewsDetailBody,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof NewsDetailBody>

export const WithToc: Story = {
  args: { content: MARKDOWN_TOC },
  decorators: [themed(false)],
}

export const Markdown: Story = {
  args: { content: MARKDOWN_SHORT },
  decorators: [themed(false)],
}

export const PlainText: Story = {
  args: { content: PLAIN_TEXT },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { content: MARKDOWN_TOC },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
