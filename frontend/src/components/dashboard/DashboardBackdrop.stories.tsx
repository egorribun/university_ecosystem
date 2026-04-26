import type { Meta, StoryObj } from '@storybook/react-vite-vite';
import { DashboardBackdrop } from './DashboardBackdrop';

const meta: Meta<typeof DashboardBackdrop> = {
  title: 'Dashboard/DashboardBackdrop',
  component: DashboardBackdrop,
  parameters: {
    layout: 'fullscreen',
  },
  decorators: [
    (Story) => (
      <div className="relative w-full h-[600px] bg-background overflow-hidden">
        <Story />
        <div className="relative z-10 p-12 text-text-primary text-center">
          <h1 className="text-4xl font-bold">Dashboard Backdrop Demo</h1>
          <p className="mt-4 text-text-secondary">This component provides the atmospheric ambient glows for the dashboard.</p>
        </div>
      </div>
    ),
  ],
  tags: ['autodocs'],
};

export default meta;
type Story = StoryObj<typeof DashboardBackdrop>;

export const Default: Story = {
  args: {
    isNarrow: false,
    prefersReducedMotion: false,
  },
};

export const Narrow: Story = {
  args: {
    isNarrow: true,
    prefersReducedMotion: false,
  },
};

export const ReducedMotion: Story = {
  args: {
    isNarrow: false,
    prefersReducedMotion: true,
  },
};
