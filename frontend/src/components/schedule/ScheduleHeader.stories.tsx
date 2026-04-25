import type { Meta, StoryObj } from '@storybook/react';
import { ScheduleHeader } from './ScheduleHeader';
import type { Lesson } from './scheduleUtils';
import type { User } from '@/types/User';

const mockUser: User = {
  id: 1,
  email: 'student@university.edu',
  full_name: 'John Doe',
  role: 'student',
  avatar_url: '',
  mfa_enabled: true,
};

const mockLessons: Lesson[] = [
  {
    id: '1',
    subject: 'Advanced Mathematics',
    teacher: 'Dr. Smith',
    room: 'Room 301',
    start_time: '08:30',
    end_time: '10:00',
    day_of_week: 1,
    lesson_type: 'lecture',
  },
  {
    id: '2',
    subject: 'Computer Science',
    teacher: 'Prof. Jones',
    room: 'Lab 1',
    start_time: '10:15',
    end_time: '11:45',
    day_of_week: 1,
    lesson_type: 'practice',
  },
];

const meta: Meta<typeof ScheduleHeader> = {
  title: 'Schedule/ScheduleHeader',
  component: ScheduleHeader,
  parameters: {
    layout: 'fullscreen',
  },
  decorators: [
    (Story) => (
      <div className="p-4 sm:p-8 bg-background min-h-[400px]">
        <Story />
      </div>
    ),
  ],
  tags: ['autodocs'],
};

export default meta;
type Story = StoryObj<typeof ScheduleHeader>;

const baseArgs = {
  user: mockUser,
  groups: [{ id: '1', name: 'CS-2024' }, { id: '2', name: 'MATH-2024' }],
  selectedGroup: '1',
  setSelectedGroup: () => {},
  currentLesson: null,
  nextLesson: null,
  timeLeftText: '',
  timeLeftShort: '',
  currentProgress: 0,
  todayLessons: mockLessons,
  nowTick: new Date(),
  onOpenSettings: () => console.log('Open settings'),
};

export const Default: Story = {
  args: baseArgs,
};

export const CurrentLesson: Story = {
  args: {
    ...baseArgs,
    currentLesson: mockLessons[0],
    currentProgress: 45,
    timeLeftText: '30 minutes remaining',
    timeLeftShort: '30m',
  },
};

export const NextLesson: Story = {
  args: {
    ...baseArgs,
    nextLesson: mockLessons[1],
    timeLeftText: 'Starts in 15 minutes',
    timeLeftShort: '15m',
  },
};

export const DayComplete: Story = {
  args: {
    ...baseArgs,
    todayLessons: [],
  },
};

export const TeacherView: Story = {
  args: {
    ...baseArgs,
    user: { ...mockUser, role: 'teacher' },
  },
};
