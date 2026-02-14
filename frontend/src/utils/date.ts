import dayjs from "dayjs"
import utc from "dayjs/plugin/utc"
import timezone from "dayjs/plugin/timezone"
import "dayjs/locale/ru"

dayjs.extend(utc)
dayjs.extend(timezone)

export const normalizeDate = (d?: string): string => (d ? d.replace("T", " ").replace("Z", "") : "")

export const getMoscowDate = (dateStr: string): string => {
  let parsed = dayjs(dateStr)
  if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(dateStr)) parsed = dayjs.utc(dateStr)
  return parsed.tz("Europe/Moscow").format("DD.MM.YYYY HH:mm")
}

export const formatLocalDateTime = (dateStr?: string): string => {
  if (!dateStr) return ""
  return dayjs(normalizeDate(dateStr).replace(" ", "T")).format("DD.MM.YYYY HH:mm")
}
