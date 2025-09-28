import React, { Suspense, lazy, useEffect, useMemo, useState } from "react";
import {
  Avatar,
  AvatarFallback,
  AvatarImage,
} from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Activity,
  Award,
  BadgeCheck,
  CalendarDays,
  CheckCircle2,
  Flame,
  Globe2,
  Link as LinkIcon,
  Mail,
  MapPin,
  MessageSquare,
  MoreHorizontal,
  PenSquare,
  ShieldCheck,
  Star,
  UserPlus,
  Users,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

type Profile = {
  id: string;
  name: string;
  handle: string;
  bio?: string;
  avatarUrl?: string;
  coverUrl?: string;
  location?: string;
  website?: string;
  joinedAt?: string;
  badges?: Array<{
    id: string;
    label: string;
    variant?: "default" | "secondary" | "outline";
  }>;
  stats: {
    followers: number;
    following: number;
    activity: number;
  };
};

type ActivityItem = {
  id: string;
  kind: "post" | "comment" | "star" | "follow";
  icon?: React.ReactNode;
  title: string;
  meta?: string;
  timestamp: string;
  cta?: {
    label: string;
    href: string;
  };
};

type Highlight = {
  id: string;
  title: string;
  description: string;
  href: string;
  icon: LucideIcon;
};

type Achievement = {
  id: string;
  title: string;
  status: "earned" | "locked";
  description: string;
  icon: LucideIcon;
  points: number;
};

type Organization = {
  id: string;
  name: string;
  role: string;
  since: string;
  logoUrl?: string;
};

type ExternalLink = {
  id: string;
  label: string;
  href: string;
  icon: LucideIcon;
};

type ContactMethod = {
  id: string;
  label: string;
  description: string;
  href: string;
  icon: LucideIcon;
};

type OverviewPanelProps = {
  profile: Profile;
  highlights: Highlight[];
};

type ActivityPanelProps = {
  items: ActivityItem[];
};

type AchievementsPanelProps = {
  achievements: Achievement[];
};

type SettingsPanelProps = {
  profile: Profile;
};

const formatNumber = new Intl.NumberFormat("en-US", {
  notation: "compact",
  compactDisplay: "short",
});

const relativeTimeFormatter = new Intl.RelativeTimeFormat("en", {
  numeric: "auto",
});

function getRelativeTime(value: string): string {
  const date = new Date(value);
  const now = Date.now();
  const diffMs = date.getTime() - now;
  const diffMinutes = Math.round(diffMs / (1000 * 60));
  if (Math.abs(diffMinutes) < 60) {
    return relativeTimeFormatter.format(diffMinutes, "minute");
  }
  const diffHours = Math.round(diffMinutes / 60);
  if (Math.abs(diffHours) < 24) {
    return relativeTimeFormatter.format(diffHours, "hour");
  }
  const diffDays = Math.round(diffHours / 24);
  if (Math.abs(diffDays) < 30) {
    return relativeTimeFormatter.format(diffDays, "day");
  }
  const diffMonths = Math.round(diffDays / 30);
  if (Math.abs(diffMonths) < 12) {
    return relativeTimeFormatter.format(diffMonths, "month");
  }
  const diffYears = Math.round(diffMonths / 12);
  return relativeTimeFormatter.format(diffYears, "year");
}

function getInitials(name: string): string {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

function usePrefersReducedMotion(): boolean {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) {
      return;
    }
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const handleChange = () => setPrefersReducedMotion(mediaQuery.matches);
    handleChange();
    mediaQuery.addEventListener("change", handleChange);
    return () => mediaQuery.removeEventListener("change", handleChange);
  }, []);
  return prefersReducedMotion;
}

const mockedProfile: Profile = {
  id: "profile-1",
  name: "Avery Bennett",
  handle: "averyb",
  bio: "Designing thoughtful student experiences at GUU. Product-minded, accessibility-first, and always ready for a campus coffee chat.",
  avatarUrl:
    "https://images.unsplash.com/photo-1521572267360-ee0c2909d518?auto=format&fit=facearea&w=300&q=80",
  coverUrl:
    "https://images.unsplash.com/photo-1521737604893-d14cc237f11d?auto=format&fit=crop&w=1600&q=80",
  location: "Glasgow, UK",
  website: "https://averyb.design",
  joinedAt: "2020-08-14T10:30:00.000Z",
  badges: [
    { id: "verified", label: "Verified", variant: "secondary" },
    { id: "pro", label: "Pro", variant: "outline" },
  ],
  stats: {
    followers: 12450,
    following: 318,
    activity: 872,
  },
};

const mockedHighlights: Highlight[] = [
  {
    id: "highlight-1",
    title: "Campus Hackathon Winner",
    description: "Led a team of 5 to build an accessibility-first campus navigation app.",
    href: "https://guu.dev/case-study",
    icon: Award,
  },
  {
    id: "highlight-2",
    title: "Student Mentor",
    description: "Mentored 20+ first-year students transitioning into tech roles.",
    href: "https://guu.dev/mentorship",
    icon: Users,
  },
];

const mockedActivity: ActivityItem[] = [
  {
    id: "activity-1",
    kind: "post",
    title: "Published a deep-dive on inclusive campus services",
    meta: "Product Journal",
    timestamp: new Date(Date.now() - 1000 * 60 * 45).toISOString(),
    cta: {
      label: "Read post",
      href: "https://guu.dev/posts/inclusion",
    },
  },
  {
    id: "activity-2",
    kind: "comment",
    title: "Commented on Sam Lee's community proposal",
    meta: "Community Forum",
    timestamp: new Date(Date.now() - 1000 * 60 * 60 * 20).toISOString(),
  },
  {
    id: "activity-3",
    kind: "star",
    title: "Starred the Sustainability Roadmap",
    meta: "Strategic Planning",
    timestamp: new Date(Date.now() - 1000 * 60 * 60 * 26).toISOString(),
  },
  {
    id: "activity-4",
    kind: "follow",
    title: "Started following Riley Chen",
    meta: "Student Affairs",
    timestamp: new Date(Date.now() - 1000 * 60 * 60 * 24 * 5).toISOString(),
    cta: {
      label: "View profile",
      href: "https://guu.dev/riley",
    },
  },
];

const mockedAchievements: Achievement[] = [
  {
    id: "achievement-1",
    title: "Campus Ambassador",
    status: "earned",
    description: "Recognized for leading three university-wide initiatives.",
    icon: BadgeCheck,
    points: 120,
  },
  {
    id: "achievement-2",
    title: "Community Builder",
    status: "earned",
    description: "Hosted monthly meetups for interdisciplinary teams.",
    icon: Users,
    points: 80,
  },
  {
    id: "achievement-3",
    title: "Innovation Sprint Finalist",
    status: "locked",
    description: "Collaborate on a prototype that reaches the final showcase.",
    icon: Activity,
    points: 60,
  },
  {
    id: "achievement-4",
    title: "Mentorship Star",
    status: "earned",
    description: "Receive 10 mentorship endorsements in a semester.",
    icon: Star,
    points: 95,
  },
  {
    id: "achievement-5",
    title: "Sustainability Advocate",
    status: "locked",
    description: "Contribute to three sustainability-focused proposals.",
    icon: Flame,
    points: 70,
  },
];

const mockedOrganizations: Organization[] = [
  {
    id: "org-1",
    name: "GUU Product Lab",
    role: "Lead Designer",
    since: "2022",
    logoUrl:
      "https://images.unsplash.com/photo-1545239351-1141bd82e8a6?auto=format&fit=crop&w=64&q=60",
  },
  {
    id: "org-2",
    name: "Accessibility Guild",
    role: "Co-founder",
    since: "2021",
    logoUrl:
      "https://images.unsplash.com/photo-1522202176988-66273c2fd55f?auto=format&fit=crop&w=64&q=60",
  },
];

const mockedLinks: ExternalLink[] = [
  {
    id: "link-1",
    label: "Portfolio",
    href: "https://averyb.design",
    icon: Globe2,
  },
  {
    id: "link-2",
    label: "Behance",
    href: "https://behance.net/averyb",
    icon: LinkIcon,
  },
  {
    id: "link-3",
    label: "Calendar",
    href: "https://cal.com/averyb",
    icon: CalendarDays,
  },
];

const mockedContactMethods: ContactMethod[] = [
  {
    id: "contact-1",
    label: "Message",
    description: "Reach out directly via inbox",
    href: "mailto:avery.bennett@guu.edu",
    icon: Mail,
  },
  {
    id: "contact-2",
    label: "Schedule",
    description: "Book a 15 minute intro chat",
    href: "https://cal.com/averyb",
    icon: CalendarDays,
  },
];

type Stat = {
  id: string;
  label: string;
  value: number;
  href: string;
  description: string;
  icon: LucideIcon;
};

const statIconMap: Record<string, LucideIcon> = {
  followers: Users,
  following: UserPlus,
  activity: Activity,
};

const activityIconMap: Record<ActivityItem["kind"], LucideIcon> = {
  post: PenSquare,
  comment: MessageSquare,
  star: Star,
  follow: UserPlus,
};

const OverviewPanel = lazy(async () => ({ default: OverviewContent }));
const ActivityPanel = lazy(async () => ({ default: ActivityTimeline }));
const AchievementsPanel = lazy(async () => ({ default: AchievementsGrid }));
const SettingsPanel = lazy(async () => ({ default: SettingsForm }));

const ProfileStat = React.memo(function ProfileStat({ stat }: { stat: Stat }) {
  const Icon = stat.icon;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          asChild
          variant="ghost"
          className="group relative flex flex-1 flex-col items-start gap-1 rounded-2xl border border-transparent px-4 py-3 text-left transition-colors focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 focus-visible:outline-none hover:border-slate-200 hover:bg-slate-50 dark:hover:border-slate-700 dark:hover:bg-slate-900"
        >
          <a href={stat.href} aria-label={`${stat.label} – ${stat.description}`}>
            <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
              <Icon className="h-4 w-4 text-sky-600 dark:text-sky-400" aria-hidden="true" />
              <span>{stat.label}</span>
            </div>
            <p className="text-2xl font-semibold text-slate-900 transition-colors group-hover:text-sky-600 dark:text-slate-100 dark:group-hover:text-sky-300">
              {formatNumber.format(stat.value)}
            </p>
          </a>
        </Button>
      </TooltipTrigger>
      <TooltipContent sideOffset={6} className="text-xs">
        {stat.description}
      </TooltipContent>
    </Tooltip>
  );
}, areStatPropsEqual);

function areStatPropsEqual(prev: { stat: Stat }, next: { stat: Stat }): boolean {
  return prev.stat.id === next.stat.id && prev.stat.value === next.stat.value;
}

const ActivityTimelineItem = React.memo(function ActivityTimelineItem({
  item,
}: {
  item: ActivityItem;
}) {
  const IconComponent = activityIconMap[item.kind];
  const iconNode = item.icon ?? (
    <IconComponent className="h-4 w-4 text-sky-500" aria-hidden="true" />
  );
  return (
    <li className="relative flex gap-4 pl-6">
      <span
        className="absolute left-0 top-2 flex h-full w-px bg-slate-200 last:h-2 dark:bg-slate-800"
        aria-hidden="true"
      />
      <span className="absolute -left-[22px] top-1 flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-950">
        {iconNode}
      </span>
      <div className="flex flex-1 flex-col gap-1 rounded-2xl border border-slate-200/70 bg-white/70 p-4 shadow-sm transition hover:border-sky-200 hover:bg-white dark:border-slate-800/80 dark:bg-slate-950/70 dark:hover:border-sky-800 dark:hover:bg-slate-900">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
            {item.title}
          </p>
          {item.meta ? (
            <Badge variant="outline" className="rounded-full border-slate-200 text-xs dark:border-slate-700">
              {item.meta}
            </Badge>
          ) : null}
        </div>
        <time
          className="text-xs text-slate-500 dark:text-slate-400"
          dateTime={item.timestamp}
        >
          {getRelativeTime(item.timestamp)}
        </time>
        {item.cta ? (
          <Button
            asChild
            variant="outline"
            size="sm"
            className="mt-2 w-fit rounded-full border-slate-200 text-xs font-medium hover:border-sky-400 hover:text-sky-600 dark:border-slate-700 dark:hover:border-sky-600 dark:hover:text-sky-400"
          >
            <a href={item.cta.href} aria-label={`${item.cta.label} – ${item.title}`}>
              {item.cta.label}
            </a>
          </Button>
        ) : null}
      </div>
    </li>
  );
}, areActivityPropsEqual);

function areActivityPropsEqual(
  prev: { item: ActivityItem },
  next: { item: ActivityItem }
): boolean {
  return prev.item.id === next.item.id && prev.item.timestamp === next.item.timestamp;
}

function OverviewContent({ profile, highlights }: OverviewPanelProps): JSX.Element {
  return (
    <div className="space-y-6">
      <Card className="rounded-2xl border border-slate-200/80 bg-white/70 shadow-sm dark:border-slate-800/80 dark:bg-slate-950/70">
        <CardHeader>
          <CardTitle className="text-lg font-semibold text-slate-900 dark:text-slate-100">
            About
          </CardTitle>
          <CardDescription className="text-sm text-slate-500 dark:text-slate-400">
            A quick introduction to {profile.name}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-sm text-slate-600 dark:text-slate-400">
          {profile.bio ? (
            <p>{profile.bio}</p>
          ) : (
            <EmptyState
              icon={MessageSquare}
              title="No bio yet"
              description="Share a little about yourself to help others connect."
              actionLabel="Add bio"
              href="#"
            />
          )}
          {profile.badges && profile.badges.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {profile.badges.map((badge) => (
                <Badge
                  key={badge.id}
                  variant={badge.variant ?? "secondary"}
                  className="rounded-full px-3 py-1 text-xs"
                >
                  {badge.label}
                </Badge>
              ))}
            </div>
          ) : null}
        </CardContent>
      </Card>
      <Card className="rounded-2xl border border-slate-200/80 bg-white/70 shadow-sm dark:border-slate-800/80 dark:bg-slate-950/70">
        <CardHeader>
          <CardTitle className="text-lg font-semibold text-slate-900 dark:text-slate-100">
            Highlights
          </CardTitle>
          <CardDescription className="text-sm text-slate-500 dark:text-slate-400">
            Featured work and achievements curated by Avery
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {highlights.length > 0 ? (
            highlights.map((highlight) => {
              const Icon = highlight.icon;
              return (
                <a
                  key={highlight.id}
                  href={highlight.href}
                  className="group flex items-start gap-3 rounded-2xl border border-slate-200/70 bg-white/60 p-4 text-left transition hover:border-sky-300 hover:bg-white dark:border-slate-800/70 dark:bg-slate-950/60 dark:hover:border-sky-700 dark:hover:bg-slate-900"
                >
                  <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-sky-50 text-sky-600 transition group-hover:bg-sky-100 dark:bg-sky-900/30 dark:text-sky-300 dark:group-hover:bg-sky-900/50">
                    <Icon className="h-5 w-5" aria-hidden="true" />
                  </span>
                  <span className="space-y-1">
                    <span className="block text-sm font-medium text-slate-900 transition group-hover:text-sky-600 dark:text-slate-100 dark:group-hover:text-sky-300">
                      {highlight.title}
                    </span>
                    <span className="block text-xs text-slate-500 dark:text-slate-400">
                      {highlight.description}
                    </span>
                  </span>
                </a>
              );
            })
          ) : (
            <EmptyState
              icon={Award}
              title="No highlights yet"
              description="Pin accomplishments and standout projects to showcase them here."
              actionLabel="Add highlight"
              href="#"
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function ActivityTimeline({ items }: ActivityPanelProps): JSX.Element {
  if (items.length === 0) {
    return (
      <EmptyState
        icon={Activity}
        title="No activity to display"
        description="When Avery shares updates or interacts with others, you'll see it here."
        actionLabel="Explore community"
        href="#"
      />
    );
  }
  return (
    <ol className="space-y-6">
      {items.map((item) => (
        <ActivityTimelineItem key={item.id} item={item} />
      ))}
    </ol>
  );
}

function AchievementsGrid({ achievements }: AchievementsPanelProps): JSX.Element {
  const [filter, setFilter] = useState<"all" | "earned" | "locked">("all");
  const filtered = useMemo(() => {
    if (filter === "all") {
      return achievements;
    }
    return achievements.filter((achievement) => achievement.status === filter);
  }, [achievements, filter]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {(
          [
            { label: "All", value: "all" as const },
            { label: "Earned", value: "earned" as const },
            { label: "Locked", value: "locked" as const },
          ] satisfies Array<{ label: string; value: "all" | "earned" | "locked" }>
        ).map((option) => (
          <Button
            key={option.value}
            variant={filter === option.value ? "default" : "outline"}
            size="sm"
            className="rounded-full border-slate-200 text-xs font-medium dark:border-slate-700"
            onClick={() => setFilter(option.value)}
          >
            {option.label}
          </Button>
        ))}
      </div>
      {filtered.length === 0 ? (
        <EmptyState
          icon={ShieldCheck}
          title="No achievements yet"
          description="Earn achievements by participating in campus initiatives."
          actionLabel="Browse opportunities"
          href="#"
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {filtered.map((achievement) => {
            const Icon = achievement.icon;
            const isLocked = achievement.status === "locked";
            return (
              <Card
                key={achievement.id}
                className="group flex h-full flex-col justify-between rounded-2xl border border-slate-200/80 bg-white/70 p-4 shadow-sm transition hover:border-sky-300 hover:bg-white dark:border-slate-800/80 dark:bg-slate-950/70 dark:hover:border-sky-700 dark:hover:bg-slate-900"
              >
                <div className="flex items-start gap-3">
                  <span
                    className="flex h-12 w-12 items-center justify-center rounded-xl bg-slate-100 text-slate-700 transition group-hover:bg-sky-100 group-hover:text-sky-600 dark:bg-slate-900 dark:text-slate-300 dark:group-hover:bg-sky-900/40 dark:group-hover:text-sky-300"
                    aria-hidden="true"
                  >
                    <Icon className="h-5 w-5" />
                  </span>
                  <div className="space-y-1">
                    <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                      {achievement.title}
                    </p>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      {achievement.description}
                    </p>
                  </div>
                </div>
                <div className="mt-4 flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
                  <span className="flex items-center gap-2">
                    <CheckCircle2
                      className={`h-4 w-4 ${isLocked ? "text-slate-400" : "text-emerald-500"}`}
                      aria-hidden="true"
                    />
                    {isLocked ? "Locked" : "Earned"}
                  </span>
                  <span className="font-semibold text-slate-900 dark:text-slate-100">
                    {achievement.points} pts
                  </span>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

function SettingsForm({ profile }: SettingsPanelProps): JSX.Element {
  const [formState, setFormState] = useState({
    name: profile.name,
    bio: profile.bio ?? "",
    website: profile.website ?? "",
    location: profile.location ?? "",
  });
  const [submitted, setSubmitted] = useState(false);

  const onChange = (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { id, value } = event.target;
    setFormState((prev) => ({ ...prev, [id]: value }));
  };

  const onSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitted(true);
  };

  const nameError = submitted && formState.name.trim().length === 0;

  return (
    <Card className="rounded-2xl border border-slate-200/80 bg-white/70 shadow-sm dark:border-slate-800/80 dark:bg-slate-950/70">
      <CardHeader>
        <CardTitle className="text-lg font-semibold text-slate-900 dark:text-slate-100">
          Profile settings
        </CardTitle>
        <CardDescription className="text-sm text-slate-500 dark:text-slate-400">
          Update how others experience your profile across the university ecosystem.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form className="space-y-4" onSubmit={onSubmit} noValidate>
          <div className="grid gap-1">
            <label
              className="text-sm font-medium text-slate-700 dark:text-slate-300"
              htmlFor="name"
            >
              Display name
            </label>
            <input
              id="name"
              value={formState.name}
              onChange={onChange}
              aria-invalid={nameError}
              aria-describedby={nameError ? "name-error" : undefined}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm transition focus-visible:border-sky-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:focus-visible:ring-sky-600"
              placeholder="Your name"
            />
            {nameError ? (
              <p id="name-error" className="text-xs text-rose-500">
                Please provide a display name.
              </p>
            ) : (
              <p className="text-xs text-slate-500 dark:text-slate-400">
                This will appear across the platform.
              </p>
            )}
          </div>
          <div className="grid gap-1">
            <label
              className="text-sm font-medium text-slate-700 dark:text-slate-300"
              htmlFor="bio"
            >
              Bio
            </label>
            <textarea
              id="bio"
              value={formState.bio}
              onChange={onChange}
              rows={4}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm transition focus-visible:border-sky-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:focus-visible:ring-sky-600"
              placeholder="Tell the community about yourself"
            />
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Keep it under 280 characters for best readability.
            </p>
          </div>
          <div className="grid gap-1">
            <label
              className="text-sm font-medium text-slate-700 dark:text-slate-300"
              htmlFor="website"
            >
              Website
            </label>
            <input
              id="website"
              value={formState.website}
              onChange={onChange}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm transition focus-visible:border-sky-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:focus-visible:ring-sky-600"
              placeholder="https://"
              inputMode="url"
              pattern="https?://.+"
            />
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Include the full URL including https://
            </p>
          </div>
          <div className="grid gap-1">
            <label
              className="text-sm font-medium text-slate-700 dark:text-slate-300"
              htmlFor="location"
            >
              Location
            </label>
            <input
              id="location"
              value={formState.location}
              onChange={onChange}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm transition focus-visible:border-sky-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:focus-visible:ring-sky-600"
              placeholder="City, Country"
            />
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Settings are preview-only for now.
            </p>
            <Button
              type="submit"
              className="rounded-full px-5"
              aria-label="Save profile settings"
            >
              Save changes
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function EmptyState({
  icon: Icon,
  title,
  description,
  actionLabel,
  href,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  actionLabel: string;
  href: string;
}): JSX.Element {
  return (
    <Card className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-slate-200/80 bg-white/60 p-6 text-center shadow-sm dark:border-slate-800/80 dark:bg-slate-950/60">
      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-700 dark:bg-slate-900 dark:text-slate-300">
        <Icon className="h-5 w-5" aria-hidden="true" />
      </span>
      <div className="space-y-1">
        <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">{title}</p>
        <p className="text-xs text-slate-500 dark:text-slate-400">{description}</p>
      </div>
      <Button
        asChild
        variant="default"
        size="sm"
        className="rounded-full"
        aria-label={`${actionLabel} – ${title}`}
      >
        <a href={href}>{actionLabel}</a>
      </Button>
    </Card>
  );
}

function HeaderSkeleton(): JSX.Element {
  return (
    <div className="space-y-4" aria-hidden="true">
      <div className="h-44 w-full overflow-hidden rounded-3xl bg-gradient-to-r from-slate-200 via-slate-100 to-slate-200 dark:from-slate-800 dark:via-slate-900 dark:to-slate-800" />
      <div className="flex flex-col gap-4 px-4 sm:px-6">
        <div className="flex items-start gap-4">
          <Skeleton className="h-32 w-32 rounded-3xl" />
          <div className="flex flex-1 flex-col gap-3">
            <Skeleton className="h-8 w-48 rounded-xl" />
            <Skeleton className="h-4 w-32" />
            <div className="flex gap-2">
              <Skeleton className="h-7 w-20 rounded-full" />
              <Skeleton className="h-7 w-16 rounded-full" />
            </div>
          </div>
        </div>
        <div className="grid gap-2 sm:grid-cols-2 md:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-4 rounded-lg" />
          ))}
        </div>
      </div>
    </div>
  );
}

function StatsSkeleton(): JSX.Element {
  return (
    <Card className="rounded-2xl border border-slate-200/80 bg-white/60 p-4 shadow-sm dark:border-slate-800/80 dark:bg-slate-950/60" aria-hidden="true">
      <div className="grid gap-4 sm:grid-cols-3">
        {Array.from({ length: 3 }).map((_, index) => (
          <div key={index} className="space-y-2">
            <Skeleton className="h-4 w-24 rounded-lg" />
            <Skeleton className="h-6 w-16 rounded-lg" />
          </div>
        ))}
      </div>
    </Card>
  );
}

function TabSkeleton(): JSX.Element {
  return (
    <div className="space-y-4" aria-hidden="true">
      {Array.from({ length: 3 }).map((_, index) => (
        <Skeleton key={index} className="h-32 w-full rounded-2xl" />
      ))}
    </div>
  );
}

function AsideSkeleton(): JSX.Element {
  return (
    <div className="space-y-4" aria-hidden="true">
      {Array.from({ length: 3 }).map((_, index) => (
        <Card
          key={index}
          className="rounded-2xl border border-slate-200/80 bg-white/60 p-4 shadow-sm dark:border-slate-800/80 dark:bg-slate-950/60"
        >
          <Skeleton className="h-6 w-32 rounded-lg" />
          <div className="mt-4 space-y-3">
            <Skeleton className="h-4 w-full rounded-lg" />
            <Skeleton className="h-4 w-3/4 rounded-lg" />
          </div>
        </Card>
      ))}
    </div>
  );
}

const statLabelMap: Record<keyof Profile["stats"], string> = {
  followers: "Followers",
  following: "Following",
  activity: "Activity",
};

const statDescriptionMap: Record<keyof Profile["stats"], string> = {
  followers: "See everyone following Avery",
  following: "People Avery follows",
  activity: "Latest posts and contributions",
};

const aboutInterests = [
  "Design Systems",
  "Accessibility",
  "Community",
  "Mentorship",
];

export default function Profile(): JSX.Element {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [highlights, setHighlights] = useState<Highlight[]>([]);
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [achievements, setAchievements] = useState<Achievement[]>([]);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [links, setLinks] = useState<ExternalLink[]>([]);
  const [contactMethods, setContactMethods] = useState<ContactMethod[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isError, setIsError] = useState(false);
  const [activeTab, setActiveTab] = useState("overview");
  const prefersReducedMotion = usePrefersReducedMotion();
  const timerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadData = React.useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }
    setIsError(false);
    setIsLoading(true);
    setProfile(null);
    setHighlights([]);
    setActivity([]);
    setAchievements([]);
    setOrganizations([]);
    setLinks([]);
    setContactMethods([]);

    if (typeof window === "undefined") {
      setProfile(mockedProfile);
      setHighlights(mockedHighlights);
      setActivity(mockedActivity);
      setAchievements(mockedAchievements);
      setOrganizations(mockedOrganizations);
      setLinks(mockedLinks);
      setContactMethods(mockedContactMethods);
      setIsLoading(false);
      return;
    }

    timerRef.current = window.setTimeout(() => {
      try {
        setProfile(mockedProfile);
        setHighlights(mockedHighlights);
        setActivity(mockedActivity);
        setAchievements(mockedAchievements);
        setOrganizations(mockedOrganizations);
        setLinks(mockedLinks);
        setContactMethods(mockedContactMethods);
        setIsLoading(false);
      } catch (error) {
        console.error(error);
        setIsError(true);
        setIsLoading(false);
      }
    }, 900);
  }, []);

  useEffect(() => {
    loadData();
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, [loadData]);

  const stats = useMemo<Stat[]>(() => {
    if (!profile) {
      return [];
    }
    return (Object.entries(profile.stats) as Array<[
      keyof Profile["stats"],
      number,
    ]>).map(([key, value]) => ({
      id: key,
      label: statLabelMap[key],
      value,
      href: `#${key}`,
      description: statDescriptionMap[key],
      icon: statIconMap[key],
    }));
  }, [profile]);

  const joinedLabel = profile?.joinedAt
    ? new Intl.DateTimeFormat("en", { month: "long", year: "numeric" }).format(
        new Date(profile.joinedAt)
      )
    : null;

  const handleRetry = () => {
    setActiveTab("overview");
    loadData();
  };

  return (
    <TooltipProvider delayDuration={prefersReducedMotion ? 0 : 200}>
      <div className="min-h-screen bg-slate-50 text-slate-900 antialiased dark:bg-slate-950 dark:text-slate-100">
        <main
          className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 pb-16 pt-8 sm:px-6 lg:px-8"
          aria-busy={isLoading}
        >
          {isLoading ? (
            <div className="space-y-6" aria-live="polite">
              <HeaderSkeleton />
              <StatsSkeleton />
              <TabSkeleton />
            </div>
          ) : isError ? (
            <Card className="rounded-2xl border border-rose-200 bg-rose-50/80 p-6 text-center shadow-sm dark:border-rose-900 dark:bg-rose-950/40">
              <CardHeader>
                <CardTitle className="text-lg font-semibold text-rose-600 dark:text-rose-300">
                  We couldn't load the profile
                </CardTitle>
                <CardDescription className="text-sm text-rose-500 dark:text-rose-200/80">
                  Something went wrong. Please try again.
                </CardDescription>
              </CardHeader>
              <CardContent className="flex justify-center">
                <Button
                  onClick={handleRetry}
                  className="rounded-full px-5"
                  aria-label="Retry loading profile"
                >
                  Retry
                </Button>
              </CardContent>
            </Card>
          ) : profile ? (
            <div
              className={`grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(260px,1fr)] ${
                prefersReducedMotion ? "" : "transition-opacity duration-700"
              }`}
            >
              <section className="space-y-6" aria-labelledby="profile-main">
                <div className="overflow-hidden rounded-3xl border border-slate-200/70 bg-white shadow-sm dark:border-slate-800/80 dark:bg-slate-950">
                  <div className="relative h-48 w-full overflow-hidden sm:h-56">
                    <div
                      className="absolute inset-0"
                      style={{
                        backgroundImage: profile.coverUrl
                          ? `linear-gradient(180deg, rgba(15,23,42,0.35), rgba(15,23,42,0.65)), url(${profile.coverUrl})`
                          : "linear-gradient(135deg, #2563eb 0%, #7c3aed 100%)",
                        backgroundSize: "cover",
                        backgroundPosition: "center",
                      }}
                      aria-hidden="true"
                    />
                  </div>
                  <div className="flex flex-col gap-6 px-4 pb-6 pt-4 sm:px-6 lg:px-8">
                    <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
                      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:gap-6">
                        <Avatar className="h-32 w-32 -translate-y-16 rounded-3xl border-4 border-white shadow-xl transition dark:border-slate-950">
                          {profile.avatarUrl ? (
                            <AvatarImage src={profile.avatarUrl} alt={profile.name} />
                          ) : null}
                          <AvatarFallback className="rounded-3xl text-2xl font-semibold">
                            {getInitials(profile.name)}
                          </AvatarFallback>
                        </Avatar>
                        <div className="flex flex-col gap-2">
                          <div>
                            <h1 id="profile-main" className="text-3xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">
                              {profile.name}
                            </h1>
                            <p className="text-sm text-slate-500 dark:text-slate-400">@{profile.handle}</p>
                          </div>
                          {profile.badges && profile.badges.length > 0 ? (
                            <div className="flex flex-wrap gap-2">
                              {profile.badges.map((badge) => (
                                <Badge
                                  key={badge.id}
                                  variant={badge.variant ?? "secondary"}
                                  className="rounded-full px-3 py-1 text-xs"
                                >
                                  {badge.label}
                                </Badge>
                              ))}
                            </div>
                          ) : null}
                        </div>
                      </div>
                      <div className="hidden w-full justify-end gap-2 sm:flex">
                        <Button
                          variant="outline"
                          className="rounded-full"
                          aria-label="Edit profile"
                        >
                          <PenSquare className="mr-2 h-4 w-4" aria-hidden="true" />
                          Edit profile
                        </Button>
                        <Button className="rounded-full" aria-label="Follow Avery Bennett">
                          <UserPlus className="mr-2 h-4 w-4" aria-hidden="true" />
                          Follow
                        </Button>
                        <Button
                          variant="outline"
                          className="rounded-full"
                          aria-label="Send Avery Bennett a message"
                        >
                          <Mail className="mr-2 h-4 w-4" aria-hidden="true" />
                          Message
                        </Button>
                      </div>
                    </div>
                    <div className="sm:hidden">
                      <div className="flex flex-col gap-2">
                        <Button className="w-full rounded-full" aria-label="Follow Avery">
                          Follow
                        </Button>
                        <div className="flex justify-end">
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button
                                size="icon"
                                variant="outline"
                                className="rounded-full"
                                aria-label="More profile actions"
                              >
                                <MoreHorizontal className="h-4 w-4" aria-hidden="true" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end" className="w-44">
                              <DropdownMenuItem>
                                <PenSquare className="mr-2 h-4 w-4" aria-hidden="true" />
                                Edit profile
                              </DropdownMenuItem>
                              <DropdownMenuItem>
                                <Mail className="mr-2 h-4 w-4" aria-hidden="true" />
                                Message
                              </DropdownMenuItem>
                              <DropdownMenuItem>
                                <ShareProfile />
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </div>
                      </div>
                    </div>
                    <Separator className="my-2 border-slate-200 dark:border-slate-800" />
                    <div className="flex flex-wrap gap-4 text-sm text-slate-600 dark:text-slate-400">
                      {profile.location ? (
                        <span className="inline-flex items-center gap-2">
                          <MapPin className="h-4 w-4" aria-hidden="true" />
                          {profile.location}
                        </span>
                      ) : null}
                      {profile.website ? (
                        <a
                          href={profile.website}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-2 text-sky-600 underline-offset-4 hover:underline dark:text-sky-400"
                        >
                          <Globe2 className="h-4 w-4" aria-hidden="true" />
                          <span className="truncate max-w-[10rem] sm:max-w-[12rem]">
                            {profile.website.replace(/^https?:\/\//, "")}
                          </span>
                        </a>
                      ) : null}
                      {profile.joinedAt && joinedLabel ? (
                        <span className="inline-flex items-center gap-2">
                          <CalendarDays className="h-4 w-4" aria-hidden="true" />
                          <time dateTime={profile.joinedAt}>Joined {joinedLabel}</time>
                        </span>
                      ) : null}
                      <span className="inline-flex items-center gap-2">
                        <span className="relative flex h-2.5 w-2.5">
                          <span
                            className={`absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75 ${
                              prefersReducedMotion ? "" : "motion-safe:animate-ping"
                            }`}
                            aria-hidden="true"
                          />
                          <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
                        </span>
                        Available for mentoring
                      </span>
                    </div>
                  </div>
                </div>
                <section aria-labelledby="profile-stats" className="space-y-3">
                  <div className="flex items-center justify-between">
                    <h2 id="profile-stats" className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                      At a glance
                    </h2>
                    <span className="text-xs text-slate-500 dark:text-slate-400">
                      Updated moments ago
                    </span>
                  </div>
                  <Card className="rounded-2xl border border-slate-200/80 bg-white/70 p-2 shadow-sm dark:border-slate-800/80 dark:bg-slate-950/70">
                    <div className="flex flex-col gap-2 sm:flex-row">
                      {stats.map((stat) => (
                        <ProfileStat key={stat.id} stat={stat} />
                      ))}
                    </div>
                  </Card>
                </section>
                <section aria-labelledby="profile-tabs" className="space-y-4">
                  <div className="flex items-center justify-between">
                    <h2 id="profile-tabs" className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                      Discover more
                    </h2>
                  </div>
                  <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
                    <nav aria-label="Profile sections" className="mb-4">
                      <TabsList className="grid w-full grid-cols-2 gap-2 rounded-2xl bg-slate-100/80 p-1 text-sm dark:bg-slate-900/60 sm:flex sm:justify-start">
                        <TabsTrigger value="overview" className="flex-1 rounded-2xl px-4 py-2">
                          Overview
                        </TabsTrigger>
                        <TabsTrigger value="activity" className="flex-1 rounded-2xl px-4 py-2">
                          Activity
                        </TabsTrigger>
                        <TabsTrigger value="achievements" className="flex-1 rounded-2xl px-4 py-2">
                          Achievements
                        </TabsTrigger>
                        <TabsTrigger value="settings" className="flex-1 rounded-2xl px-4 py-2">
                          Settings
                        </TabsTrigger>
                      </TabsList>
                    </nav>
                    <TabsContent value="overview" className="outline-none">
                      <Suspense fallback={<TabSkeleton />}>
                        <OverviewPanel profile={profile} highlights={highlights} />
                      </Suspense>
                    </TabsContent>
                    <TabsContent value="activity" className="outline-none">
                      <Suspense fallback={<TabSkeleton />}>
                        <ActivityPanel items={activity} />
                      </Suspense>
                    </TabsContent>
                    <TabsContent value="achievements" className="outline-none">
                      <Suspense fallback={<TabSkeleton />}>
                        <AchievementsPanel achievements={achievements} />
                      </Suspense>
                    </TabsContent>
                    <TabsContent value="settings" className="outline-none">
                      <Suspense fallback={<TabSkeleton />}>
                        <SettingsPanel profile={profile} />
                      </Suspense>
                    </TabsContent>
                  </Tabs>
                </section>
              </section>
              <aside className="hidden space-y-4 lg:block" aria-label="Profile right rail">
                <div className="sticky top-24 space-y-4">
                  <Card className="rounded-2xl border border-slate-200/80 bg-white/70 shadow-sm dark:border-slate-800/80 dark:bg-slate-950/70">
                    <CardHeader>
                      <CardTitle className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                        About Avery
                      </CardTitle>
                      <CardDescription className="text-xs text-slate-500 dark:text-slate-400">
                        Quick context for collaborators
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3 text-sm text-slate-600 dark:text-slate-400">
                      <p>
                        Avery focuses on human-centered service design and frequently partners with student clubs to deliver delightful experiences.
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {aboutInterests.map((interest) => (
                          <Badge key={interest} variant="secondary" className="rounded-full px-3 py-1 text-xs">
                            {interest}
                          </Badge>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                  <Card className="rounded-2xl border border-slate-200/80 bg-white/70 shadow-sm dark:border-slate-800/80 dark:bg-slate-950/70">
                    <CardHeader>
                      <CardTitle className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                        Organizations
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      {organizations.length > 0 ? (
                        organizations.map((organization) => (
                          <div key={organization.id} className="flex items-center gap-3">
                            <Avatar className="h-10 w-10 rounded-xl">
                              {organization.logoUrl ? (
                                <AvatarImage src={organization.logoUrl} alt={organization.name} />
                              ) : (
                                <AvatarFallback className="rounded-xl text-xs font-semibold">
                                  {organization.name
                                    .split(" ")
                                    .map((part) => part[0])
                                    .join("")}
                                </AvatarFallback>
                              )}
                            </Avatar>
                            <div className="min-w-0">
                              <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
                                {organization.name}
                              </p>
                              <p className="text-xs text-slate-500 dark:text-slate-400">
                                {organization.role} · since {organization.since}
                              </p>
                            </div>
                          </div>
                        ))
                      ) : (
                        <p className="text-xs text-slate-500 dark:text-slate-400">
                          No organization memberships listed yet.
                        </p>
                      )}
                    </CardContent>
                  </Card>
                  <Card className="rounded-2xl border border-slate-200/80 bg-white/70 shadow-sm dark:border-slate-800/80 dark:bg-slate-950/70">
                    <CardHeader>
                      <CardTitle className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                        Links
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      {links.length > 0 ? (
                        links.map((link) => (
                          <Button
                            key={link.id}
                            asChild
                            variant="ghost"
                            className="w-full justify-start rounded-2xl border border-transparent px-3 py-2 text-sm font-medium hover:border-sky-200 hover:bg-sky-50 dark:hover:border-sky-700 dark:hover:bg-slate-900"
                          >
                            <a href={link.href} target="_blank" rel="noopener noreferrer">
                              <span className="flex items-center gap-2">
                                <link.icon className="h-4 w-4 text-sky-500" aria-hidden="true" />
                                {link.label}
                              </span>
                            </a>
                          </Button>
                        ))
                      ) : (
                        <p className="text-xs text-slate-500 dark:text-slate-400">No external links yet.</p>
                      )}
                    </CardContent>
                  </Card>
                  <Card className="rounded-2xl border border-slate-200/80 bg-white/70 shadow-sm dark:border-slate-800/80 dark:bg-slate-950/70">
                    <CardHeader>
                      <CardTitle className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                        Contact
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      {contactMethods.length > 0 ? (
                        contactMethods.map((method) => (
                          <Button
                            key={method.id}
                            asChild
                            variant="outline"
                            className="w-full justify-start rounded-2xl border-slate-200 px-3 py-2 text-sm hover:border-sky-300 hover:text-sky-600 dark:border-slate-700 dark:hover:border-sky-600 dark:hover:text-sky-300"
                          >
                            <a href={method.href} aria-label={`${method.label} – ${method.description}`}>
                              <span className="flex items-center gap-2">
                                <method.icon className="h-4 w-4" aria-hidden="true" />
                                <span className="flex-1 text-left">
                                  <span className="block font-medium">{method.label}</span>
                                  <span className="block text-xs text-slate-500 dark:text-slate-400">
                                    {method.description}
                                  </span>
                                </span>
                              </span>
                            </a>
                          </Button>
                        ))
                      ) : (
                        <p className="text-xs text-slate-500 dark:text-slate-400">No contact methods listed.</p>
                      )}
                    </CardContent>
                  </Card>
                </div>
              </aside>
            </div>
          ) : (
            <AsideSkeleton />
          )}
        </main>
      </div>
    </TooltipProvider>
  );
}
function ShareProfile(): JSX.Element {
  return (
    <span className="flex items-center">
      <LinkIcon className="mr-2 h-4 w-4" aria-hidden="true" />
      Share profile
    </span>
  );
}

