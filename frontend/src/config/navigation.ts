import DashboardIcon from "@mui/icons-material/Dashboard"
import ArticleIcon from "@mui/icons-material/Article"
import CalendarMonthIcon from "@mui/icons-material/CalendarMonth"
import EventNoteIcon from "@mui/icons-material/EventNote"
import TimelineIcon from "@mui/icons-material/Timeline"
import MapIcon from "@mui/icons-material/Map"
import NotificationsIcon from "@mui/icons-material/Notifications"
import AutoStoriesIcon from "@mui/icons-material/AutoStories"
import PeopleIcon from "@mui/icons-material/People"
import FlagIcon from "@mui/icons-material/Flag"
import SecurityIcon from "@mui/icons-material/Security"

export const getNavigationConfig = (t: (key: string) => string, role?: string) => {
  const base = [
    { to: "/dashboard", label: t("navigation:menu.dashboard"), icon: DashboardIcon },
    { to: "/news", label: t("navigation:menu.news"), icon: ArticleIcon },
    { to: "/schedule", label: t("navigation:menu.schedule"), icon: CalendarMonthIcon },
    { to: "/events", label: t("navigation:menu.events"), icon: EventNoteIcon },
    { to: "/activity", label: t("navigation:menu.activity"), icon: TimelineIcon },
    { to: "/map", label: t("navigation:menu.map"), icon: MapIcon },
  ]
  if (role === "admin") {
    base.push({
      to: "/admin/notifications",
      label: t("navigation:menu.notificationsAdmin"),
      icon: NotificationsIcon,
    })
    base.push({
      to: "/admin/stories",
      label: t("navigation:menu.stories"),
      icon: AutoStoriesIcon,
    })
    base.push({
      to: "/admin/users",
      label: t("navigation:menu.users"),
      icon: PeopleIcon,
    })
    base.push({
      to: "/admin/feature-flags",
      label: t("navigation:menu.featureFlags"),
      icon: FlagIcon,
    })
    base.push({
      to: "/admin/audit",
      label: t("navigation:menu.audit"),
      icon: SecurityIcon,
    })
  }
  return base
}
