import type { Meta, StoryObj } from '@storybook/react';
import { EventFormDialog } from './EventFormDialog';

const meta: Meta<typeof EventFormDialog> = {
  title: 'Features/Events/EventFormDialog',
  component: EventFormDialog,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
};

export default meta;
type Story = StoryObj<typeof EventFormDialog>;

export const Default: Story = {
  args: {
    open: true,
    onClose: () => console.log('Close'),
    onSuccess: () => console.log('Success'),
    language: 'ru',
  },
};

export const English: Story = {
  args: {
    open: true,
    onClose: () => console.log('Close'),
    onSuccess: () => console.log('Success'),
    language: 'en',
  },
};
