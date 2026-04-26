import type { Meta, StoryObj } from '@storybook/react-vite-vite';
import { ScheduleMiniCalendar } from './ScheduleMiniCalendar';

const meta: Meta<typeof ScheduleMiniCalendar> = {
  title: 'Schedule/ScheduleMiniCalendar',
  component: ScheduleMiniCalendar,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
};

export default meta;
type Story = StoryObj<typeof ScheduleMiniCalendar>;

export const Default: Story = {
  args: {
    lessonDays: new Set([1, 5, 12, 15, 20, 25]),
  },
};

export const Loading: Story = {
  args: {
    isLoading: true,
  },
};

export const SpecificMonth: Story = {
  args: {
    month: new Date(2024, 0, 1), // January 2024
    lessonDays: new Set([10, 11, 12]),
  },
};
