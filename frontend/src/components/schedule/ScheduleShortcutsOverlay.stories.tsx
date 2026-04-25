import type { Meta, StoryObj } from '@storybook/react';
import { ScheduleShortcutsOverlay } from './ScheduleShortcutsOverlay';

const meta: Meta<typeof ScheduleShortcutsOverlay> = {
  title: 'Schedule/ScheduleShortcutsOverlay',
  component: ScheduleShortcutsOverlay,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
};

export default meta;
type Story = StoryObj<typeof ScheduleShortcutsOverlay>;

export const Default: Story = {
  args: {
    open: true,
    onClose: () => console.log('Close'),
  },
};
