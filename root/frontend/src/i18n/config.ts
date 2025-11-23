import i18n from "i18next"
import { initReactI18next } from "react-i18next"

import commonEn from "./locales/en/common.json" assert { type: "json" }
import commonRu from "./locales/ru/common.json" assert { type: "json" }
import navigationEn from "./locales/en/navigation.json" assert { type: "json" }
import navigationRu from "./locales/ru/navigation.json" assert { type: "json" }
import dashboardEn from "./locales/en/dashboard.json" assert { type: "json" }
import dashboardRu from "./locales/ru/dashboard.json" assert { type: "json" }
import activityEn from "./locales/en/activity.json" assert { type: "json" }
import activityRu from "./locales/ru/activity.json" assert { type: "json" }
import scheduleEn from "./locales/en/schedule.json" assert { type: "json" }
import scheduleRu from "./locales/ru/schedule.json" assert { type: "json" }
import authEn from "./locales/en/auth.json" assert { type: "json" }
import authRu from "./locales/ru/auth.json" assert { type: "json" }
import settingsEn from "./locales/en/settings.json" assert { type: "json" }
import settingsRu from "./locales/ru/settings.json" assert { type: "json" }
import systemEn from "./locales/en/system.json" assert { type: "json" }
import systemRu from "./locales/ru/system.json" assert { type: "json" }
import newsEn from "./locales/en/news.json" assert { type: "json" }
import newsRu from "./locales/ru/news.json" assert { type: "json" }
import eventsEn from "./locales/en/events.json" assert { type: "json" }
import eventsRu from "./locales/ru/events.json" assert { type: "json" }
import profileEn from "./locales/en/profile.json" assert { type: "json" }
import profileRu from "./locales/ru/profile.json" assert { type: "json" }
import notificationsEn from "./locales/en/notifications.json" assert { type: "json" }
import notificationsRu from "./locales/ru/notifications.json" assert { type: "json" }
import adminEn from "./locales/en/admin.json" assert { type: "json" }
import adminRu from "./locales/ru/admin.json" assert { type: "json" }
import storiesEn from "./locales/en/stories.json" assert { type: "json" }
import storiesRu from "./locales/ru/stories.json" assert { type: "json" }
import messengerEn from "./locales/en/messenger.json" assert { type: "json" }
import messengerRu from "./locales/ru/messenger.json" assert { type: "json" }

export const defaultNS = "common"

export const resources = {
  en: {
    common: commonEn,
    navigation: navigationEn,
    dashboard: dashboardEn,
    activity: activityEn,
    schedule: scheduleEn,
    auth: authEn,
    settings: settingsEn,
    system: systemEn,
    news: newsEn,
    events: eventsEn,
    profile: profileEn,
    notifications: notificationsEn,
    admin: adminEn,
    stories: storiesEn,
    messenger: messengerEn,
  },
  ru: {
    common: commonRu,
    navigation: navigationRu,
    dashboard: dashboardRu,
    activity: activityRu,
    schedule: scheduleRu,
    auth: authRu,
    settings: settingsRu,
    system: systemRu,
    news: newsRu,
    events: eventsRu,
    profile: profileRu,
    notifications: notificationsRu,
    admin: adminRu,
    stories: storiesRu,
    messenger: messengerRu,
  },
} as const

export const supportedLngs = ["en", "ru"] as const

export const fallbackLng = "en"

void i18n.use(initReactI18next).init({
  resources,
  defaultNS,
  fallbackLng,
  supportedLngs: [...supportedLngs],
  lng: "ru",
  interpolation: {
    escapeValue: false,
  },
  react: {
    useSuspense: false,
  },
  returnNull: false,
})

export default i18n
