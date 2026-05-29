import { useState } from "react"
import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import {
  SectionCard,
  SectionTitle,
  SectionSubtitle,
  SessionItem,
  AccordionSection,
  Divider,
  Tabs,
  Tab,
} from "./Layout"

// Wave 199 SW1 — settings/ui Layout composite (CONTEXT-tier, no infra).
//
// Compound module: SectionCard/Title/Subtitle + SessionItem + AccordionSection +
// Divider + Tabs/Tab. AccordionSection (m.svg) and Tab (m.div layoutId) use
// framer-motion → LazyMotion required. Tabs is controlled via local state in the
// composite harness. Inline, no portal, no network on mount.
//
// Variants: Default / DarkMode.

const LayoutComposite = () => {
  const [tab, setTab] = useState(0)
  return (
    <div className="space-y-6">
      <SectionCard>
        <SectionTitle>Аккаунт</SectionTitle>
        <SectionSubtitle>Управляйте профилем и безопасностью.</SectionSubtitle>
        <Divider />
        <SessionItem>
          <div>
            <p className="font-semibold text-text-primary">Chrome · Windows</p>
            <p className="text-sm text-(--text-secondary)">Москва · текущая сессия</p>
          </div>
        </SessionItem>
        <SessionItem revoked>
          <div>
            <p className="font-semibold text-text-primary">Safari · iPhone</p>
            <p className="text-sm text-(--text-secondary)">Сессия завершена</p>
          </div>
        </SessionItem>
      </SectionCard>

      <AccordionSection
        title="Расширенные настройки"
        subtitle="Редко изменяемые параметры"
        defaultExpanded
      >
        <p className="text-sm text-(--text-secondary)">
          Экспериментальные флаги и инструменты разработчика.
        </p>
      </AccordionSection>

      <Tabs value={tab} onChange={(_, v) => setTab(v)} ariaLabel="Разделы настроек">
        <Tab label="Общие" />
        <Tab label="Аккаунт" />
        <Tab label="Безопасность" />
      </Tabs>
    </div>
  )
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div className="settings-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
          <div style={{ width: 520 }}>
            <Story />
          </div>
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof SectionCard> = {
  title: "Settings/UI/Layout",
  component: SectionCard,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
  render: () => <LayoutComposite />,
}

export default meta
type Story = StoryObj<typeof SectionCard>

export const Default: Story = { decorators: [themed(false)] }

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
