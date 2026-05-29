import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import type { ComponentProps } from "react"
import { useTranslation } from "react-i18next"
import { getMoscowDate } from "@/utils/date"
import type { NewsComment } from "@/hooks/useNewsInteraction"
import { NewsComments } from "./NewsComments"

// Wave 197 SW1 — NewsComments Storybook fixture (CONTEXT-tier, cheap/ambient).
//
// Comment thread for a news article: list + inline edit/delete (owner or admin)
// + new-comment form (when signed in) + delete ConfirmDialog. Fully prop-driven —
// `t` and `getMoscowDate` are passed in as props, so a tiny harness supplies the
// real i18n `t` (via useTranslation, resolved by the global I18nextProvider) and
// the real getMoscowDate util. No theme scope beyond globals.
//
// Variants: WithComments (admin → edit/delete + form) / Empty (no comments, form
// visible) / Anonymous (no user → read-only, no form, no row actions).

type HarnessProps = Pick<ComponentProps<typeof NewsComments>, "comments" | "user" | "isCommenting">

function CommentsHarness({ comments, user, isCommenting }: HarnessProps) {
  const { t } = useTranslation(["news", "common"])
  return (
    <NewsComments
      comments={comments}
      user={user}
      isCommenting={isCommenting}
      addComment={() => {}}
      updateComment={() => {}}
      deleteComment={() => {}}
      t={t}
      getMoscowDate={getMoscowDate}
    />
  )
}

const SAMPLE_COMMENTS: NewsComment[] = [
  {
    id: "c1",
    content: "Great write-up — the interdisciplinary angle is exactly what the campus needed.",
    user_id: "u2",
    user_name: "Anna Petrova",
    created_at: "2026-05-20T09:30:00Z",
  },
  {
    id: "c2",
    content: "Thanks for the detail on the robotics track. Any word on enrollment caps?",
    user_id: "u3",
    user_name: "Ivan Sokolov",
    created_at: "2026-05-21T14:15:00Z",
  },
  {
    id: "c3",
    content: "When does the lab open to undergraduates?",
    user_id: "u4",
    user_name: "Maria Volkova",
    created_at: "2026-05-22T08:00:00Z",
  },
]

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div className="news-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div style={{ maxWidth: 640, margin: "0 auto" }}>
          <Story />
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof NewsComments> = {
  title: "News/NewsComments",
  component: NewsComments,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof NewsComments>

export const WithComments: Story = {
  render: () => (
    <CommentsHarness
      comments={SAMPLE_COMMENTS}
      user={{ id: "u1", role: "admin" }}
      isCommenting={false}
    />
  ),
  decorators: [themed(false)],
}

export const Empty: Story = {
  render: () => (
    <CommentsHarness comments={[]} user={{ id: "u1", role: "student" }} isCommenting={false} />
  ),
  decorators: [themed(false)],
}

export const Anonymous: Story = {
  render: () => <CommentsHarness comments={SAMPLE_COMMENTS} user={null} isCommenting={false} />,
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  render: () => (
    <CommentsHarness
      comments={SAMPLE_COMMENTS}
      user={{ id: "u1", role: "admin" }}
      isCommenting={false}
    />
  ),
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
