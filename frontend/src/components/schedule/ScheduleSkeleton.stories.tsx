import type { Meta, StoryObj } from '@storybook/react';
import { ScheduleSkeleton } from './ScheduleSkeleton';

const meta: Meta<typeof ScheduleSkeleton> = {
  title: 'Schedule/ScheduleSkeleton',
  component: ScheduleSkeleton,
  parameters: {
    layout: 'fullscreen',
  },
  tags: ['autodocs'],
};

export default meta;
type Story = StoryObj<typeof ScheduleSkeleton>;

export const Default: Story = {};
