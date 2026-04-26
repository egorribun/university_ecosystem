import type { Meta, StoryObj } from '@storybook/react-vite-vite';
import { ClockWidget } from './ClockWidget';

const meta: Meta<typeof ClockWidget> = {
  title: 'Dashboard/ClockWidget',
  component: ClockWidget,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
};

export default meta;
type Story = StoryObj<typeof ClockWidget>;

export const Default: Story = {
  decorators: [
    (Story) => (
      <div style={{ width: '320px', height: '200px' }}>
        <Story />
      </div>
    ),
  ],
};
