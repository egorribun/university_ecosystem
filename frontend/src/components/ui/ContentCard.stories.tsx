import type { Decorator, Meta, StoryObj } from "@storybook/react-vite"
import { ContentCard } from "./ContentCard"

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div className="group" style={{ maxWidth: 360, margin: "0 auto" }}>
          <Story />
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof ContentCard> = {
  title: "UI/ContentCard",
  component: ContentCard,
  tags: ["autodocs"],
  parameters: { layout: "fullscreen" },
}

export default meta
type Story = StoryObj<typeof ContentCard>

export const Default: Story = {
  render: () => (
    <ContentCard>
      <ContentCard.Media src="https://picsum.photos/seed/content-card/640/360" alt="" />
      <ContentCard.Header>
        <ContentCard.Title>Modern Web Development Workshop</ContentCard.Title>
        <ContentCard.Actions>
          <ContentCard.Badge variant="info">New</ContentCard.Badge>
        </ContentCard.Actions>
      </ContentCard.Header>
      <ContentCard.Body>
        A hands-on session covering React 19, Vite, and accessible component patterns.
      </ContentCard.Body>
      <ContentCard.Footer>
        <span className="text-xs text-(--text-secondary)">20 May · Hall B</span>
      </ContentCard.Footer>
    </ContentCard>
  ),
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  render: () => (
    <ContentCard>
      <ContentCard.Media src="https://picsum.photos/seed/content-card/640/360" alt="" />
      <ContentCard.Header>
        <ContentCard.Title>Modern Web Development Workshop</ContentCard.Title>
      </ContentCard.Header>
      <ContentCard.Body>A hands-on session covering React 19 + Vite.</ContentCard.Body>
    </ContentCard>
  ),
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
